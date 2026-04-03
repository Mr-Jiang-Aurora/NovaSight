"""
指标提取验证器
负责将原始提取结果写入 PaperRecord.scores 字段，
并进行数值范围验证（过滤明显错误的数值）。
"""

from __future__ import annotations

import logging
from typing import Optional

from shared.models import PaperRecord, MetricScores, ExtractionConfidence

logger = logging.getLogger(__name__)

# 系统认可的标准指标名称集合（各解析器和验证器共同使用）
VALID_METRICS: frozenset[str] = frozenset({
    "Sm", "Em", "Fm", "MAE", "maxFm", "avgFm", "wFm",
})


class MetricExtractor:
    """指标提取与验证器"""

    def write_scores(
        self,
        paper: PaperRecord,
        raw_tables: list[dict],
        domain: str,
        confidence: ExtractionConfidence,
    ) -> bool:
        """
        将原始表格数据写入 PaperRecord.scores 字段。

        Args:
            paper:      目标论文记录
            raw_tables: 原始提取结果（来自各级解析器）
                        每个元素格式：{"dataset": str, "metrics": {std_name: float}}
            domain:     研究领域（用于获取有效范围配置）
            confidence: 本次提取的置信度

        Returns:
            True 表示至少写入了一个有效指标，False 表示全部验证失败
        """
        from config.knowledge_base import DOMAIN_KNOWLEDGE_BASE

        domain_info  = DOMAIN_KNOWLEDGE_BASE.get(domain, {})
        valid_ranges = domain_info.get("valid_ranges", {})
        any_valid    = False

        for table in raw_tables:
            dataset     = table.get("dataset", "Unknown")
            metrics_raw = table.get("metrics", {})

            validated: dict[str, float] = {}
            for metric_name, value in metrics_raw.items():
                if not isinstance(value, (int, float)):
                    continue

                # 过滤非标准指标名（未被 normalize_metric_name 识别的原始列名）
                if metric_name not in VALID_METRICS:
                    logger.debug(
                        f"未识别指标名（已跳过）：'{metric_name}' "
                        f"不在 VALID_METRICS 中 | 论文: {paper.title[:40]}"
                    )
                    continue

                # 数值范围验证
                range_cfg = valid_ranges.get(metric_name)
                if range_cfg:
                    lo, hi = range_cfg
                    if not (lo <= value <= hi):
                        logger.warning(
                            f"指标越界过滤：{paper.title[:30]} | "
                            f"{dataset}.{metric_name}={value} "
                            f"（有效范围 [{lo}, {hi}]）"
                        )
                        continue

                validated[metric_name] = value

            if validated:
                # 构造 MetricScores 对象
                score_obj = MetricScores(
                    confidence=confidence,
                    raw_values=validated,
                )
                # 填充标准字段（Sm / Em / Fm / MAE / maxFm / avgFm / wFm）
                for metric, val in validated.items():
                    if hasattr(score_obj, metric):
                        setattr(score_obj, metric, val)

                paper.scores[dataset] = score_obj
                any_valid = True
                logger.debug(
                    f"写入分数：{paper.title[:30]} | "
                    f"{dataset}: {validated}"
                )

        if any_valid:
            paper.scores_extracted = True

        return any_valid
