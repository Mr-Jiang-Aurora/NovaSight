"""
方法强弱特征画像生成器
对每篇有分数的论文，计算其在各数据集×指标上的排名百分位，
识别相对强项和弱项。
"""

import logging

from shared.models import PaperRecord, MethodProfile, DatasetRanking

logger = logging.getLogger(__name__)


class Profiler:
    """方法强弱特征画像生成器"""

    def profile_all(
        self,
        papers: list[PaperRecord],
        rankings: list[DatasetRanking],
        scorer,
    ) -> list[MethodProfile]:
        """
        为所有有分数的论文生成画像。

        Returns:
            MethodProfile 列表，按综合得分降序排列
        """
        scored_papers = [p for p in papers if p.scores]
        profiles = [
            self._profile_one(paper, rankings, scorer)
            for paper in scored_papers
        ]
        profiles.sort(key=lambda p: p.overall_score, reverse=True)
        return profiles

    def _profile_one(
        self,
        paper: PaperRecord,
        rankings: list[DatasetRanking],
        scorer,
    ) -> MethodProfile:

        profile = MethodProfile(
            paper_id=paper.paper_id or "",
            title=paper.title or "",
            venue=paper.venue,
            year=paper.year,
        )

        # 计算在每个排行榜中的排名百分位
        for ranking in rankings:
            dataset = ranking.dataset
            metric  = ranking.metric
            n       = len(ranking.entries)
            if n == 0:
                continue

            paper_rank = next(
                (e.rank for e in ranking.entries
                 if e.paper_id == (paper.paper_id or "")),
                None,
            )
            if paper_rank is None:
                continue

            # rank=1（最好）→ percentile=0.0；rank=n → percentile=1.0
            percentile = (paper_rank - 1) / max(n - 1, 1)

            if dataset not in profile.rank_percentiles:
                profile.rank_percentiles[dataset] = {}
            profile.rank_percentiles[dataset][metric] = round(percentile, 3)

        # 综合得分
        profile.overall_score = scorer.compute_score(paper)

        # 识别最强/最弱（基于百分位：越低越强）
        all_pcts = [
            (ds, metric, pct)
            for ds, metric_map in profile.rank_percentiles.items()
            for metric, pct in metric_map.items()
        ]

        if all_pcts:
            best  = min(all_pcts, key=lambda x: x[2])
            worst = max(all_pcts, key=lambda x: x[2])
            profile.strongest_dataset = best[0]
            profile.strongest_metric  = best[1]
            profile.weakest_dataset   = worst[0]
            profile.weakest_metric    = worst[1]

        return profile
