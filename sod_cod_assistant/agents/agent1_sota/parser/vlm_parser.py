"""
级别 D：VLM 兜底解析器（Claude Sonnet）
将 PDF 页面渲染为高分辨率图片，发送给 Claude Vision 进行表格识别。
适用于：旋转表格、图片内嵌表格、极复杂布局等级别 A/B/C 均失败的情形。
成本较高（每次 API 调用约 0.01-0.05 USD），请谨慎使用。

支持中转服务商 URL（通过 ANTHROPIC_BASE_URL 配置），
支持自定义模型（通过 ANTHROPIC_MODEL 配置）。
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Optional

import fitz  # PyMuPDF，用于渲染页面图片

logger = logging.getLogger(__name__)


# 专为 SOTA 表格提取设计的 VLM Prompt（降幻觉优化版）
VLM_SYSTEM_PROMPT = """你是一个专业的学术论文表格数据提取助手。
你的任务是从论文截图中精确提取 COD/SOD 方向的 SOTA 对比表格数据。

提取规则：
1. 只提取数值型指标（Sm/Em/Fm/MAE/maxFm/avgFm 及其变体写法）
2. 对于旋转 90° 的表格，请先识别旋转方向，再读取数据
3. 如果数值大于 1，说明是百分比格式（如 86.2），请除以 100 得到小数（0.862）
4. 只提取你**确定**看到的数值，不确定的一律不填（宁可少填，不可编造）
5. 输出必须是合法的 JSON，不加任何额外文字

输出格式（严格遵守）：
{
  "tables": [
    {
      "dataset": "数据集名称（如 COD10K/CAMO/NC4K/CHAMELEON）",
      "metrics": {
        "Sm": 0.862,
        "Em": 0.912,
        "MAE": 0.031
      }
    }
  ],
  "confidence": "high/medium/low",
  "notes": "如有旋转或特殊情况，在此说明"
}

如果图片中没有 SOTA 对比表格，或完全无法读取，输出：
{"tables": [], "confidence": "low", "notes": "原因说明"}"""


class VLMParser:
    """Claude Vision VLM 兜底解析器（级别 D）"""

    RENDER_DPI = 300  # 渲染分辨率（越高越清晰，但图片越大）

    def __init__(self, settings) -> None:
        """
        初始化 VLM 解析器（双提供商版）。
        根据 ACTIVE_AI_PROVIDER 自动选择 Claude 或 OpenAI。
        """
        from shared.ai_caller import get_ai_caller, get_active_provider
        self._settings = settings
        self._caller   = get_ai_caller(settings)
        provider       = get_active_provider(settings)

        if provider == "openai":
            enabled = bool(getattr(settings, "OPENAI_API_KEY", ""))
        else:
            enabled = bool(getattr(settings, "ANTHROPIC_API_KEY", ""))

        if not enabled:
            raise ValueError(f"{provider} API Key 未配置，VLM 级别 D 无法使用")

        logger.info(f"[VLM] 初始化完成：provider={provider}")

    def parse(
        self,
        pdf_path: str,
        candidate_pages: list[int],
        dataset_names: list[str],
        is_rotated: bool = False,
    ) -> Optional[list[dict]]:
        """
        渲染 PDF 候选页为图片，调用 Claude Vision 提取表格。

        Args:
            pdf_path:        PDF 文件路径
            candidate_pages: 候选页码列表（只处理前 2 页，控制成本）
            dataset_names:   目标数据集名
            is_rotated:      是否已知表格旋转（True 时在 Prompt 中特别提示）

        Returns:
            提取结果列表（每个元素为 {dataset, metrics}），或 None（提取失败）
        """
        from config.knowledge_base import normalize_metric_name

        # 最多处理 2 页（控制 API 成本）
        pages_to_process = candidate_pages[:2]

        all_results = []
        for page_num in pages_to_process:
            image_b64 = self._render_page_to_b64(pdf_path, page_num)
            if not image_b64:
                continue

            extracted = self._call_vlm(
                image_b64, dataset_names, is_rotated, normalize_metric_name
            )
            if extracted:
                all_results.extend(extracted)

        return all_results if all_results else None

    def _render_page_to_b64(self, pdf_path: str, page_num: int) -> Optional[str]:
        """将 PDF 页面渲染为 PNG 图片并转为 base64"""
        try:
            doc = fitz.open(pdf_path)
            if page_num >= len(doc):
                doc.close()
                return None

            page = doc[page_num]
            # 使用高 DPI 渲染（300 DPI 保证表格文字清晰）
            mat = fitz.Matrix(self.RENDER_DPI / 72, self.RENDER_DPI / 72)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            img_bytes = pix.tobytes("png")
            doc.close()

            return base64.standard_b64encode(img_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"[VLM] 页面渲染失败（页 {page_num}）: {e}")
            return None

    def _call_vlm(
        self,
        image_b64: str,
        dataset_names: list[str],
        is_rotated: bool,
        normalize_fn,
    ) -> Optional[list[dict]]:
        """调用 Claude Vision API 提取表格数据（普通模式，无需 thinking 参数）"""
        user_prompt = (
            f"请从这张论文截图中提取 SOTA 对比表格数据。\n"
            f"目标数据集：{', '.join(dataset_names)}\n"
        )
        if is_rotated:
            user_prompt += "注意：该表格可能旋转了 90°，请先判断旋转方向再读取数据。\n"

        try:
            from shared.ai_caller import get_ai_caller
            caller = get_ai_caller(self._settings)
            raw_text, is_fatal = caller.chat(
                system=VLM_SYSTEM_PROMPT,
                user_content=user_prompt,
                max_tokens=1000,
                image_data={"base64": image_b64, "media_type": "image/png"},
            )

            if is_fatal:
                logger.error(f"[VLM] API 不可恢复错误：{raw_text[:100]}")
                return None

            if not raw_text:
                logger.warning("[VLM] API 返回内容为空")
                return None

            # 提取 JSON（去除可能的 markdown code block）
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if not json_match:
                logger.warning(f"[VLM] 返回非 JSON 格式：{raw_text[:200]}")
                return None

            data = json.loads(json_match.group())
            tables = data.get("tables", [])
            confidence = data.get("confidence", "low")

            if confidence == "low" or not tables:
                logger.debug(f"[VLM] 低置信度或无表格：{data.get('notes', '')}")
                return None

            # 标准化指标名称
            results = []
            for table in tables:
                metrics: dict[str, float] = {}
                for metric_raw, val in table.get("metrics", {}).items():
                    std = normalize_fn(metric_raw)
                    if val is not None:
                        try:
                            v = float(val)
                            # 大于 1 说明是百分比格式，转为小数
                            if v > 1.0:
                                v = v / 100.0
                            metrics[std] = round(v, 4)
                        except (ValueError, TypeError):
                            continue
                if metrics:
                    results.append({
                        "dataset": table.get("dataset", "Unknown"),
                        "metrics": metrics,
                    })

            return results if results else None

        except json.JSONDecodeError as e:
            logger.error(f"[VLM] 返回 JSON 解析失败: {e}")
            return None
        except Exception as e:
            # 保留回退入口（兼容未来可能切换回 thinking 模型）
            if "thinking" in str(e).lower() or "budget_tokens" in str(e).lower():
                logger.warning(f"[VLM] thinking 参数不支持，回退普通模式：{e}")
                return self._call_vlm_plain(
                    image_b64, dataset_names, is_rotated, normalize_fn
                )
            logger.error(f"[VLM] API 调用失败: {e}")
            return None

    def _call_vlm_plain(
        self,
        image_b64: str,
        dataset_names: list[str],
        is_rotated: bool,
        normalize_fn,
    ) -> Optional[list[dict]]:
        """
        不使用 thinking 参数的普通调用（回退方案）。
        当中转服务商或旧版本 API 不支持 extended thinking 时使用。
        """
        user_prompt = (
            f"请从这张论文截图中提取 SOTA 对比表格数据。\n"
            f"目标数据集：{', '.join(dataset_names)}\n"
        )
        if is_rotated:
            user_prompt += "注意：该表格可能旋转了 90°，请先判断旋转方向再读取数据。\n"

        try:
            from shared.ai_caller import get_ai_caller
            caller = get_ai_caller(self._settings)
            raw_text, is_fatal = caller.chat(
                system=VLM_SYSTEM_PROMPT,
                user_content=user_prompt,
                max_tokens=2000,
                image_data={"base64": image_b64, "media_type": "image/png"},
            )

            if is_fatal or not raw_text:
                logger.error(f"[VLM] 普通模式 API 失败")
                return None

            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if not json_match:
                return None

            data = json.loads(json_match.group())
            tables = data.get("tables", [])
            confidence = data.get("confidence", "low")
            if confidence == "low" or not tables:
                return None

            results = []
            for table in tables:
                metrics: dict[str, float] = {}
                for metric_raw, val in table.get("metrics", {}).items():
                    std = normalize_fn(metric_raw)
                    if val is not None:
                        try:
                            v = float(val)
                            if v > 1.0:
                                v = v / 100.0
                            metrics[std] = round(v, 4)
                        except (ValueError, TypeError):
                            continue
                if metrics:
                    results.append({
                        "dataset": table.get("dataset", "Unknown"),
                        "metrics": metrics,
                    })

            return results if results else None

        except Exception as e:
            logger.error(f"[VLM] 普通模式调用也失败: {e}")
            return None
