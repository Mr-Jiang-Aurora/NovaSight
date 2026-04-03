"""
综合得分计算器
默认复现 Excel 公式：(Sm+Em+Fm)/3 - MAE（按数据集独立计算再等权平均）。
支持自定义指标权重与数据集权重。
"""

import logging
from typing import Optional

from shared.models import PaperRecord

logger = logging.getLogger(__name__)


class Scorer:
    """综合得分计算器"""

    def __init__(
        self,
        datasets: list[str],
        metric_weights: Optional[dict[str, float]] = None,
        dataset_weights: Optional[dict[str, float]] = None,
    ):
        """
        Args:
            datasets:        参与评分的数据集列表
            metric_weights:  各指标权重（None 则使用 Excel 公式）
            dataset_weights: 各数据集权重（None 则等权平均）
        """
        self.datasets = datasets

        # 默认：复现 Excel 公式 (Sm+Em+Fm)/3 - MAE
        self.metric_weights = metric_weights or {
            "Sm":  1 / 3,
            "Em":  1 / 3,
            "Fm":  1 / 3,
            "MAE": -1.0,   # 负号：越低越好，直接减去
        }

        n = len(datasets)
        self.dataset_weights = dataset_weights or {
            ds: 1.0 / n for ds in datasets
        }

    def compute_score(self, paper: PaperRecord) -> float:
        """计算单篇论文的综合得分。"""
        if not paper.scores:
            return 0.0

        dataset_scores = []
        for dataset in self.datasets:
            if dataset not in paper.scores:
                continue
            score_obj = paper.scores[dataset]
            ds_score   = 0.0
            weight_sum = 0.0

            for metric, weight in self.metric_weights.items():
                value = getattr(score_obj, metric, None)
                if value is None:
                    continue
                ds_score   += weight * value
                weight_sum += abs(weight)

            if weight_sum > 0:
                ds_weight = self.dataset_weights.get(dataset, 1.0)
                dataset_scores.append(ds_score * ds_weight)

        if not dataset_scores:
            return 0.0

        return round(sum(dataset_scores), 6)

    def rank_all(
        self, papers: list[PaperRecord]
    ) -> list[tuple[PaperRecord, float]]:
        """对所有论文计算综合得分并降序排序。"""
        results = [(p, self.compute_score(p)) for p in papers if p.scores]
        results.sort(key=lambda x: x[1], reverse=True)
        return results
