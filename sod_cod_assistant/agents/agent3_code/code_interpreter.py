"""
Agent3 代码语义理解 + 深度改进建议生成器（深度升级版）

升级内容：
1. max_tokens 从 1500 → 4000，允许完整深度分析
2. 代码上下文从 250 行 → 5000 行，覆盖完整模型结构
3. System Prompt 强约束：强制逐文件分析、禁止套话
4. 质量自检 + 自动重试（最多 2 次）
5. 分析结构化为六个模块（新增「风险评估」和「实现路线图」）
"""

import json
import re
import logging
from typing import Optional
import anthropic
import httpx

from shared.models import UserCodeAnalysis, ImprovementSuggestion

logger = logging.getLogger(__name__)


# ══ 强约束 System Prompt ═════════════════════════════════════════════

CODE_ANALYSIS_SYSTEM = """你是一位在 CVPR/ICCV/TPAMI 发表过多篇 COD/SOD 论文的资深研究员，
同时精通 PyTorch 深度学习工程实现。

你的任务是对用户提交的 COD/SOD 模型代码进行深度分析，
输出结构化的架构诊断和可操作的改进建议。

━━━ 强制分析规范（违反即不合格，需重写）━━━

【规范1】必须逐文件分析
对每个传入的代码文件，必须明确说明：
  - 该文件的功能定位（主网络/损失函数/配置/训练脚本）
  - 在该文件中识别到的具体类名、函数名（配行号）
  - 该文件实现的架构组件

【规范2】架构描述必须精确到模块级别
  ✗ 不合格："使用了 Transformer 架构"
  ✓ 合格："主干网络为 SwinTransformer（models/backbone/swin.py，第34行 class SwinTransformer），
           通过 forward_features() 提取 4 个尺度的特征图（C1-C4），
           输出通道数分别为 [96, 192, 384, 768]"

【规范3】损失函数必须量化
  ✗ 不合格："使用了多种损失函数"
  ✓ 合格："structure_loss = BCE_loss + weight_iou * iou_loss（train.py 第87行），
           其中 weight_iou=1.0；额外添加了 edge_loss（权重=0.3），
           总损失 = structure_loss + 0.3 * edge_loss"

【规范4】每条改进建议必须有三要素
  要素1 — 具体问题（从代码中找到的）：如"decoder 仅使用最后一层特征，丢失了浅层细节"
  要素2 — 改进方案（技术细节）：如"添加跨层跳跃连接，融合 C1/C2 的浅层特征"
  要素3 — 参考实现（现有 SOTA）：如"参考 CamoDiffusion 的多尺度特征融合策略"

【规范5】改进建议数量：5-8 条，按优先级分 high/medium/low 排列
  high 优先级：能直接影响指标提升的改动（如损失函数、backbone 升级）
  medium 优先级：架构改进（如注意力模块、特征融合方式）
  low 优先级：工程优化（如训练策略、数据增强）

【规范6】必须给出 SOTA 差距的量化估计
  不能说"与SOTA有差距"，要说"当前方案预计 COD10K Sm ≈ 0.83-0.85，
  与 SOTA CamoDiffusion（0.880）差距约 0.03-0.05，
  主要差距来源分析：…"

━━━ 输出格式（严格的 JSON，不加任何额外文字）━━━

{
  "arch_summary": "精确的一句话架构描述（含backbone名称、decoder类型、核心创新模块）",
  "framework": "PyTorch/TensorFlow/etc",

  "file_analysis": [
    {
      "file": "文件路径",
      "role": "该文件的功能（主网络/损失函数/配置/训练/backbone）",
      "key_classes": ["类名1（行号）", "类名2（行号）"],
      "key_functions": ["函数名1（行号）", "函数名2（行号）"],
      "arch_contribution": "该文件实现的架构贡献描述"
    }
  ],

  "components": [
    {
      "type": "backbone/neck/decoder/head/module",
      "name": "标准化名称",
      "detail": "精确描述（含文件路径、类名、行号）",
      "is_pretrained": true,
      "pretrained_on": "ImageNet-22K 或 null"
    }
  ],

  "loss_analysis": {
    "total_loss_formula": "完整损失公式（如 L = L_bce + λ1*L_iou + λ2*L_edge）",
    "components": [
      {
        "name": "损失名称",
        "weight": 1.0,
        "location": "文件路径:行号",
        "is_auxiliary": false
      }
    ],
    "assessment": "损失函数设计的评价（2-3句，有数值支撑）"
  },

  "train_config": {
    "batch_size": null,
    "learning_rate": null,
    "optimizer": "名称",
    "lr_scheduler": "名称",
    "epochs": null,
    "input_size": null,
    "config_source": "配置来源文件"
  },

  "key_innovations": [
    "创新点1：[类名/函数名，文件:行号] — 具体说明这个创新做了什么"
  ],

  "potential_issues": [
    "问题1：[具体位置] — 问题描述 — 可能导致的影响"
  ],

  "suggestions": [
    {
      "category": "backbone/loss/architecture/training/data",
      "priority": "high/medium/low",
      "problem": "从代码中找到的具体问题（含文件路径）",
      "suggestion": "具体改进方案（技术细节，不是套话）",
      "reference": "参考的 SOTA 方法和论文",
      "code_hint": "代码修改提示（如：修改 models/net.py 第X行，添加...）",
      "estimated_gain": "预计指标提升量（如：COD10K Sm +0.01~0.02）"
    }
  ],

  "sota_gap_analysis": {
    "estimated_performance": "预计当前方案的性能范围（如 COD10K Sm ≈ 0.83-0.86）",
    "gap_to_sota": "与当前 SOTA 的差距（如 Delta ≈ 0.02-0.05）",
    "main_gap_sources": ["差距来源1", "差距来源2"],
    "improvement_roadmap": "达到 SOTA 水平的关键步骤（按优先级排序，3-5步）"
  }
}

规则：
- 只分析代码中真实存在的内容，不编造类名或行号
- 所有涉及文件路径的信息必须来自传入的代码，不能凭空推断
- 如果某个字段无法从代码中确定，填 null，不要瞎填"""


# ══ 质量自检 ════════════════════════════════════════════════════════

QUALITY_CHECKS = [
    ("包含 file_analysis",    lambda d: bool(d.get("file_analysis"))),
    ("包含 components",       lambda d: bool(d.get("components"))),
    ("包含 loss_analysis",    lambda d: bool(d.get("loss_analysis"))),
    ("包含 suggestions(>=5)", lambda d: len(d.get("suggestions", [])) >= 5),
    ("包含 sota_gap_analysis",lambda d: bool(d.get("sota_gap_analysis"))),
    ("arch_summary 不为空",   lambda d: len(d.get("arch_summary", "")) > 20),
]


def quality_check(data: dict) -> tuple[bool, list[str]]:
    failures = []
    for desc, check_fn in QUALITY_CHECKS:
        try:
            if not check_fn(data):
                failures.append(f"未通过：{desc}")
        except Exception as e:
            failures.append(f"检查异常（{desc}）：{e}")
    return len(failures) == 0, failures


# ══ 主类 ════════════════════════════════════════════════════════════

class CodeInterpreter:
    """代码语义理解 + 深度改进建议生成器（双提供商版）"""

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
            logger.warning(f"[CodeInterpreter] {provider} API Key 未配置，代码语义理解将跳过")

    def interpret(
        self,
        analysis:       "UserCodeAnalysis",
        file_contents:  dict[str, str],
        sota_context:   str = "",
        structure_hint: str = "",
        max_code_lines: int = 10000,   # 总行数上限：1万行（约30个文件 × 333行）
        max_retries:    int = 1,
    ) -> None:
        """
        调用 AI API 进行深度代码分析。
        结果直接更新 analysis 对象。
        """
        if not self.enabled:
            analysis.arch_summary = "（代码语义理解未启用）"
            self._fallback_summary(analysis)
            return

        code_ctx = self._build_code_context(file_contents, max_code_lines)
        logger.info(f"[CodeInterpreter] 代码上下文：约 {len(code_ctx)//1000}K 字符，"
                    f"共 {code_ctx.count(chr(10))} 行")

        data = None
        last_raw = ""
        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info(f"[CodeInterpreter] 质量不足，第 {attempt} 次重试")

            raw, is_fatal = self._call_claude(code_ctx, sota_context, structure_hint, attempt)
            last_raw = raw or ""

            if is_fatal:
                logger.warning("[CodeInterpreter] 遇到不可恢复 API 错误，停止重试")
                analysis.arch_summary = raw
                self._fallback_summary(analysis)
                return

            if not raw:
                logger.warning(f"[CodeInterpreter] API 返回空内容（尝试 {attempt+1}）")
                continue

            data = self._parse_json(raw)
            if data is None:
                logger.warning(
                    f"[CodeInterpreter] JSON 解析失败（尝试 {attempt+1}），"
                    f"响应前300字：{raw[:300]}"
                )
                continue

            passed, failures = quality_check(data)
            if passed:
                logger.info(f"[CodeInterpreter] 质量检查通过（尝试 {attempt + 1} 次）")
                self._update_analysis(analysis, data)
                return
            else:
                logger.warning(f"[CodeInterpreter] 质量不足：{failures}")

        # 达到最大重试次数，使用最终版本
        if data:
            self._update_analysis(analysis, data)
            logger.warning("[CodeInterpreter] 达到最大重试次数，使用最终版本")
        else:
            # AI 分析完全失败，从静态分析生成基础摘要
            logger.warning("[CodeInterpreter] AI 分析未产生有效结果，使用静态分析 fallback")
            self._fallback_summary(analysis)

    def _call_claude(
        self,
        code_ctx:       str,
        sota_context:   str,
        structure_hint: str,
        attempt:        int,
    ) -> str:
        retry_note = ""
        if attempt > 0:
            retry_note = (
                "\n\n【重试要求】上次分析质量不达标，请特别注意：\n"
                "1. file_analysis 必须对每个文件单独分析\n"
                "2. suggestions 必须 >= 5 条，每条含 problem/suggestion/reference/code_hint\n"
                "3. sota_gap_analysis 必须包含量化的性能预估\n"
                "4. 所有类名/函数名必须来自代码，不能推断"
            )

        parts = []
        if structure_hint:
            parts.append(f"【目录结构提示（来自图像识别）】\n{structure_hint}\n")

        parts.append(f"【待分析代码（关键文件）】\n{code_ctx}\n")

        if sota_context:
            parts.append(f"【当前领域 SOTA 参考数据（用于差距分析）】\n{sota_context}\n")

        parts.append(
            "请对以上代码进行深度分析，严格按照规范输出 JSON。"
            + retry_note
        )

        from shared.ai_caller import get_ai_caller, get_active_provider
        caller = get_ai_caller(self._settings)
        provider = get_active_provider(self._settings)
        logger.info(f"[CodeInterpreter] 使用提供商: {provider}")
        return caller.chat(
            system=CODE_ANALYSIS_SYSTEM,
            user_content="\n".join(parts),
            max_tokens=10000,
        )

    def _parse_json(self, raw: str) -> Optional[dict]:
        """从 Claude 输出中提取并解析 JSON"""
        if not raw:
            return None
        # 1. 直接解析
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # 2. 提取 ```json ... ``` 代码块（贪婪，支持超长 JSON）
        match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 3. 直接找最外层 { ... }（贪婪）
        start = raw.find('{')
        end   = raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass
        logger.error(f"无法解析 JSON，原始输出前200字：{raw[:200]}")
        return None

    def _update_analysis(
        self, analysis: "UserCodeAnalysis", data: dict
    ) -> None:
        """将解析后的 JSON 数据更新到 analysis 对象"""
        analysis.arch_summary     = data.get("arch_summary", "")
        analysis.framework        = data.get("framework") or analysis.framework
        analysis.key_innovations  = data.get("key_innovations", [])
        analysis.potential_issues = data.get("potential_issues", [])

        # 更新 components
        from shared.models import ArchComponent
        for c in data.get("components", []):
            analysis.components.append(ArchComponent(
                component_type = c.get("type", "module"),
                name           = c.get("name", ""),
                source_file    = c.get("detail", ""),
                is_pretrained  = c.get("is_pretrained", False),
                pretrained_on  = c.get("pretrained_on"),
            ))

        # 更新 losses（来自 loss_analysis）
        from shared.models import LossConfig
        loss_data = data.get("loss_analysis", {})
        for lc in loss_data.get("components", []):
            analysis.losses.append(LossConfig(
                loss_name    = lc.get("name", ""),
                weight       = float(lc.get("weight", 1.0) or 1.0),
                source_file  = lc.get("location", ""),
                is_auxiliary = lc.get("is_auxiliary", False),
            ))

        # 更新 train_config
        tc_data = data.get("train_config", {})
        if tc_data:
            from shared.models import TrainConfig
            analysis.train_config = TrainConfig(
                batch_size    = tc_data.get("batch_size"),
                learning_rate = tc_data.get("learning_rate"),
                optimizer     = tc_data.get("optimizer"),
                lr_scheduler  = tc_data.get("lr_scheduler"),
                epochs        = tc_data.get("epochs"),
                input_size    = tc_data.get("input_size"),
                config_file   = tc_data.get("config_source", ""),
            )

        # 更新 suggestions，把 problem 和 estimated_gain 追加到文字里
        from shared.models import ImprovementSuggestion
        for s in data.get("suggestions", []):
            problem = s.get("problem", "")
            gain    = s.get("estimated_gain", "")
            base    = s.get("suggestion", "")
            full_text = (
                f"[问题] {problem}\n[方案] {base}\n[预计收益] {gain}"
                if (problem or gain) else base
            )
            analysis.suggestions.append(ImprovementSuggestion(
                category   = s.get("category",  "architecture"),
                priority   = s.get("priority",  "medium"),
                suggestion = full_text,
                reference  = s.get("reference", ""),
                code_hint  = s.get("code_hint", ""),
            ))

        # 更新 SOTA 差距摘要
        gap = data.get("sota_gap_analysis", {})
        if gap:
            analysis.sota_gap_summary = (
                f"预计性能：{gap.get('estimated_performance', '-')}\n"
                f"与SOTA差距：{gap.get('gap_to_sota', '-')}\n"
                f"主要差距来源：{', '.join(gap.get('main_gap_sources', []))}\n"
                f"改进路线图：{gap.get('improvement_roadmap', '-')}"
            )

        # 把 file_analysis 追加到 key_innovations（供报告输出）
        for fa in data.get("file_analysis", []):
            role    = fa.get("role", "")
            classes = ", ".join(fa.get("key_classes", []))
            contrib = fa.get("arch_contribution", "")
            if classes or contrib:
                analysis.key_innovations.append(
                    f"[{fa.get('file', '')}（{role}）] "
                    f"关键类：{classes} | {contrib}"
                )

    def _fallback_summary(self, analysis: "UserCodeAnalysis") -> None:
        """当 AI 分析失败时，从静态分析结果生成基础架构摘要"""
        if analysis.arch_summary:
            return  # 已有内容，不覆盖

        parts = []

        # Backbone
        backbones = [c.name for c in analysis.components
                     if getattr(c, "component_type", "") == "backbone"]
        if backbones:
            parts.append(f"主干网络：{', '.join(backbones)}")

        # Decoder/module
        modules = [c.name for c in analysis.components
                   if getattr(c, "component_type", "") in ("decoder", "module")]
        if modules:
            parts.append(f"关键模块：{', '.join(modules[:4])}")

        # 损失函数
        losses = [l.loss_name for l in analysis.losses]
        if losses:
            parts.append(f"损失函数：{', '.join(losses[:4])}")

        # 框架
        fw = analysis.framework or "PyTorch"
        parts.append(f"框架：{fw}")

        if parts:
            analysis.arch_summary = "（静态分析）" + "；".join(parts)
            logger.info(f"[CodeInterpreter] fallback 摘要：{analysis.arch_summary}")
        else:
            analysis.arch_summary = "（未能解析架构信息）"

    def _build_code_context(
        self, file_contents: dict[str, str], max_lines: int
    ) -> str:
        """
        构建传给 Claude 的代码上下文（最多 max_lines 行）。
        优先顺序：主网络 > 损失函数 > decoder > backbone > 配置 > 其他。
        """
        def priority(path: str) -> int:
            p = path.lower()
            if any(x in p for x in ["net.py", "model.py", "network.py", "camonet", "codnet"]):
                return 0
            if any(x in p for x in ["loss", "criterion"]):
                return 1
            if any(x in p for x in ["decoder", "head"]):
                return 2
            if any(x in p for x in ["backbone", "encoder"]):
                return 3
            if any(x in p for x in ["config", "train", "option"]):
                return 4
            return 5

        sorted_files = sorted(file_contents.items(), key=lambda x: priority(x[0]))

        parts = []
        total = 0
        for path, content in sorted_files:
            if total >= max_lines:
                break
            lines   = content.splitlines()
            remain  = max_lines - total
            snippet = "\n".join(lines[:remain])
            truncated = len(lines) > remain
            parts.append(
                f"# === 文件：{path} ({'已截断' if truncated else '完整'}) ===\n"
                f"{snippet}"
            )
            total += min(len(lines), remain)

        return "\n\n".join(parts)
