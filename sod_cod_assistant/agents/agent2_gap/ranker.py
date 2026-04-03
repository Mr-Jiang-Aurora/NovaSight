"""
多维度排行榜计算器
对每个数据集 × 每个指标，生成独立排行榜。
支持 CCF 分层过滤（只看 A 类、只看 B 类，或全部）。
"""

import logging
from typing import Optional

from shared.models import PaperRecord, DatasetRanking, RankEntry

logger = logging.getLogger(__name__)


# 指标方向：True = 越高越好，False = 越低越好
METRIC_DIRECTION: dict[str, bool] = {
    "Sm":    True,
    "Em":    True,
    "Fm":    True,
    "maxFm": True,
    "avgFm": True,
    "wFm":   True,
    "MAE":   False,
}


class Ranker:
    """多维度排行榜计算器"""

    def compute_all_rankings(
        self,
        papers: list[PaperRecord],
        datasets: list[str],
        metrics: list[str],
        ccf_filter: Optional[str] = None,
    ) -> list[DatasetRanking]:
        """
        对所有数据集 × 指标组合生成排行榜。

        Args:
            papers:     论文列表
            datasets:   目标数据集（如 ["COD10K","CAMO","NC4K"]）
            metrics:    目标指标（如 ["Sm","Em","Fm","MAE"]）
            ccf_filter: CCF 等级过滤（None 表示不过滤）

        Returns:
            DatasetRanking 列表
        """
        if ccf_filter:
            papers = [p for p in papers if p.ccf_rank == ccf_filter]
            logger.info(f"CCF-{ccf_filter} 过滤后：{len(papers)} 篇")

        all_rankings = []
        for dataset in datasets:
            for metric in metrics:
                ranking = self._compute_single_ranking(papers, dataset, metric)
                if ranking.entries:
                    all_rankings.append(ranking)

        logger.info(
            f"排行榜计算完成：{len(all_rankings)} 个（"
            f"{len(datasets)} 数据集 × {len(metrics)} 指标）"
        )
        return all_rankings

    def _compute_single_ranking(
        self,
        papers: list[PaperRecord],
        dataset: str,
        metric: str,
    ) -> DatasetRanking:
        """计算单个数据集×指标的排行榜"""
        is_higher_better = METRIC_DIRECTION.get(metric, True)

        data_points = []
        for paper in papers:
            if not paper.scores or dataset not in paper.scores:
                continue
            score_obj = paper.scores[dataset]
            value = getattr(score_obj, metric, None)
            if value is None:
                continue
            data_points.append((paper, value))

        data_points.sort(key=lambda x: x[1], reverse=is_higher_better)

        entries = [
            RankEntry(
                rank=rank,
                paper_id=paper.paper_id or "",
                title=paper.title or "",
                venue=paper.venue,
                year=paper.year,
                ccf_rank=paper.ccf_rank,
                value=round(value, 4),
                paper_url=paper.paper_url,
                code_url=paper.code_url,
            )
            for rank, (paper, value) in enumerate(data_points, 1)
        ]

        return DatasetRanking(
            dataset=dataset,
            metric=metric,
            direction="up" if is_higher_better else "down",
            entries=entries,
        )

    def get_top_n(
        self,
        rankings: list[DatasetRanking],
        dataset: str,
        metric: str,
        n: int = 5,
    ) -> list[RankEntry]:
        """快速获取某数据集某指标的 Top N"""
        for r in rankings:
            if r.dataset == dataset and r.metric == metric:
                return r.entries[:n]
        return []
