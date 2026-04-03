"""
模式2：可视化对比图深度分析器（升级版）
对多方法预测结果对比图进行逐行样本分析和跨方法对比。

升级内容：
1. max_tokens 2000 → 3000
2. 强制逐行样本分析、失败模式分类
3. JSON 结构扩展（含 evidence、failure_mode、cross_method_findings、metric_alignment）
4. 质量自检 + 自动重试（最多 2 次）
"""

import json
import re
import logging
from typing import Optional
import anthropic
import httpx

from shared.models import VisualAnalysis, ColumnAnalysis

logger = logging.getLogger(__name__)


VISUAL_ANALYSIS_SYSTEM = """你是一位 COD/SOD 图像分割领域的专家评审，
擅长通过视觉对比发现方法间的性能差异，
能将视觉观察与 Sm/Em/Fm/MAE 等指标联系起来分析。

你的任务是对多方法预测结果对比图进行深度分析。

━━━ 强制分析规范（违反任何一条即不合格，系统将自动重试）━━━

【规范1】每个评分必须有具体图像证据（行号 + 场景描述）
  ✗ 不合格："边缘锐利度3分"
  ✓ 合格："边缘锐利度3分：第2行（树枝场景）边缘晕染约3-5px，第4行基本准确"

【规范2】必须识别困难样本和简单样本
  哪些行各方法普遍失败（困难样本）？
  哪些行各方法普遍成功（简单样本）？
  困难样本的视觉特征是什么？

【规范3】必须对每个方法分类失败模式
  漏检型（整块目标缺失）/虚检型（背景误判）/
  边缘模糊型/形状错误型/综合型/无明显失败

【规范4】必须给出至少2个跨方法对比发现
  格式："方法X在[第N行/Y类场景]明显胜过方法Z：原因"

【规范5】必须分析视觉结果与指标数据的对应关系

━━━ 输出格式（严格 JSON，不加任何其他文字）━━━

{
  "image_count": 列总数,
  "row_count": 行总数,
  "difficult_rows": [困难样本行号列表],
  "easy_rows": [简单样本行号列表],
  "difficult_characteristics": "困难样本的共同视觉特征描述",

  "columns": [
    {
      "column_index": 0,
      "method_name": "方法名（从图中列标题读取，没有则用 Method_N）",
      "is_reference": true或false（原图和GT标为true）,
      "edge_sharpness": null或1-5,
      "bg_cleanliness": null或1-5,
      "target_completeness": null或1-5,
      "shape_accuracy": null或1-5,
      "failure_mode": "漏检型/虚检型/边缘模糊型/形状错误型/综合型/无失败/参考列",
      "evidence": "评分的具体图像证据（行号+场景+观察到的具体现象）",
      "strengths": ["优势1（含行号）"],
      "weaknesses": ["劣势1（含行号）"],
      "overall_desc": "2-3句综合描述"
    }
  ],

  "cross_method_findings": [
    "方法A在第N行（场景描述）中边缘锐利度明显优于方法B：具体描述差异"
  ],

  "best_method": "最优方法名",
  "worst_method": "最差方法名（排除参考列）",
  "key_findings": ["发现1（有方法名和行号）", "发现2"],
  "metric_alignment": "视觉结果与指标排序的一致性分析",
  "improvement_focus": "改进建议（具体到失败模式和对应的技术方向）"
}"""


VISUAL_QUALITY_CHECKS = [
    ("包含 difficult_rows",
     lambda d: "difficult_rows" in d),
    ("columns 每个含 evidence",
     lambda d: all(
         isinstance(c, dict) and len(c.get("evidence", "")) > 10
         for c in d.get("columns", [{}])
         if not c.get("is_reference", False)
     )),
    ("columns 每个含 failure_mode",
     lambda d: all(
         isinstance(c, dict) and c.get("failure_mode")
         for c in d.get("columns", [{}])
         if not c.get("is_reference", False)
     )),
    ("cross_method_findings 不为空",
     lambda d: len(d.get("cross_method_findings", [])) >= 2),
    ("包含 metric_alignment",
     lambda d: len(d.get("metric_alignment", "")) > 10),
]


def visual_quality_check(data: dict) -> tuple[bool, list[str]]:
    failures = []
    for desc, check_fn in VISUAL_QUALITY_CHECKS:
        try:
            if not check_fn(data):
                failures.append(f"未通过：{desc}")
        except Exception as e:
            failures.append(f"检查异常（{desc}）：{e}")
    return len(failures) == 0, failures


class VisualComparator:
    """可视化对比图深度分析器（双提供商版）"""

    def __init__(self, settings):
        from shared.ai_caller import get_ai_caller, get_active_provider
        self._settings = settings
        self._caller   = get_ai_caller(settings)
        provider       = get_active_provider(settings)

        if provider == "openai":
            self.enabled = bool(getattr(settings, "OPENAI_API_KEY", ""))
        else:
            self.enabled = bool(getattr(settings, "ANTHROPIC_API_KEY", ""))

        if not self.enabled:
            logger.warning(f"[VisualComparator] {provider} API Key 未配置，可视化对比将跳过")

    def analyze(
        self,
        image_data:  dict,
        user_method: str = "",
        user_hint:   str = "",
        max_retries: int = 2,
    ) -> VisualAnalysis:
        va = VisualAnalysis(image_path=image_data.get("path", ""))

        if not self.enabled:
            return va

        data = None
        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info(f"[VisualComparator] 质量不足，第 {attempt} 次重试")

            raw, is_fatal = self._call_claude(image_data, user_method, user_hint, attempt)
            if is_fatal:
                logger.warning("[VisualComparator] 遇到不可恢复 API 错误，停止重试")
                return va

            data = self._parse_json(raw)
            if data is None:
                continue

            passed, failures = visual_quality_check(data)
            if passed:
                logger.info(f"[VisualComparator] 质量检查通过（尝试 {attempt + 1} 次）")
                self._update_visual(va, data, user_method)
                return va
            else:
                logger.warning(f"[VisualComparator] 质量不足：{failures}")

        if data:
            self._update_visual(va, data, user_method)
            logger.warning("[VisualComparator] 达到最大重试次数，使用最终版本")
        return va

    def _call_claude(
        self,
        image_data:  dict,
        user_method: str,
        user_hint:   str,
        attempt:     int,
    ) -> str:
        retry_note = ""
        if attempt > 0:
            retry_note = (
                "\n\n【重试要求】：\n"
                "1. columns 中每个非参考列必须有 evidence 字段（具体行号+现象）\n"
                "2. cross_method_findings 必须 >= 2 条具体对比发现\n"
                "3. 必须识别 difficult_rows（困难样本行号）\n"
                "请重新仔细观察图片中的每一行。"
            )

        parts = [
            "请对这张多方法预测结果对比图进行深度分析，"
            "必须逐行分析，每个评分必须有具体图像证据。"
        ]
        if user_method:
            parts.append(
                f"「{user_method}」是用户自己的方法，请重点分析其优劣势。"
            )
        if user_hint:
            parts.append(f"补充说明：{user_hint}")
        if retry_note:
            parts.append(retry_note)

        from shared.ai_caller import get_ai_caller, get_active_provider
        caller = get_ai_caller(self._settings)
        logger.info(f"[VisualComparator] 使用提供商: {get_active_provider(self._settings)}")
        return caller.chat(
            system=VISUAL_ANALYSIS_SYSTEM,
            user_content="\n".join(parts),
            max_tokens=8000,
            image_data=image_data,
        )

    def _parse_json(self, raw: str) -> Optional[dict]:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # 提取 ```json ... ``` 代码块（贪婪，支持超长 JSON）
        match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 找最外层 { ... }
        start = raw.find('{')
        end   = raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass
        logger.error(f"JSON 解析失败，原始输出：{raw[:200]}")
        return None

    def _update_visual(
        self, va: VisualAnalysis, data: dict, user_method: str
    ) -> None:
        va.image_count       = data.get("image_count", 0)
        va.row_count         = data.get("row_count", 0)
        va.best_method       = data.get("best_method", "")
        va.worst_method      = data.get("worst_method", "")
        va.key_findings      = data.get("key_findings", [])
        va.improvement_focus = data.get("improvement_focus", "")

        # 跨方法对比发现 → 追加到 key_findings
        cross = data.get("cross_method_findings", [])
        if cross:
            va.key_findings = va.key_findings + [f"[跨方法对比] {c}" for c in cross]

        # 指标对应关系 → 追加到 key_findings
        metric_align = data.get("metric_alignment", "")
        if metric_align:
            va.key_findings.append(f"[指标一致性] {metric_align}")

        for col_data in data.get("columns", []):
            col = ColumnAnalysis(
                column_index        = col_data.get("column_index", 0),
                method_name         = col_data.get("method_name", ""),
                edge_sharpness      = col_data.get("edge_sharpness") or 0,
                bg_cleanliness      = col_data.get("bg_cleanliness") or 0,
                target_completeness = col_data.get("target_completeness") or 0,
                shape_accuracy      = col_data.get("shape_accuracy") or 0,
                strengths           = col_data.get("strengths", []),
                weaknesses          = col_data.get("weaknesses", []),
                overall_desc        = col_data.get("overall_desc", ""),
            )
            evidence     = col_data.get("evidence", "")
            failure_mode = col_data.get("failure_mode", "")
            if evidence:
                col.overall_desc += f"\n证据：{evidence}"
            if failure_mode:
                col.overall_desc += f"\n失败模式：{failure_mode}"
            va.columns.append(col)

        # 识别用户方法排名
        if user_method:
            pred_cols = [
                c for c in va.columns
                if c.method_name not in ("Input", "GT", "")
                and any([c.edge_sharpness, c.bg_cleanliness,
                         c.target_completeness, c.shape_accuracy])
            ]
            scored = sorted(
                pred_cols,
                key=lambda c: (
                    c.edge_sharpness + c.bg_cleanliness
                    + c.target_completeness + c.shape_accuracy
                ),
                reverse=True
            )
            for rank, col in enumerate(scored, 1):
                if col.method_name == user_method:
                    va.user_method_rank = rank
                    break
