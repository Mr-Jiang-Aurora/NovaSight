"""
差距与进步率分析器
分析各年度 SOTA 的变化趋势，判断指标是否趋于饱和。
"""

import logging
from collections import defaultdict

from shared.models import PaperRecord, GapAnalysis

logger = logging.getLogger(__name__)


class GapAnalyzer:
    """差距与进步率分析器"""

    def analyze(
        self,
        papers: list[PaperRecord],
        datasets: list[str],
        metrics: list[str],
        domain: str,
    ) -> list[GapAnalysis]:
        """
        对每个数据集执行差距分析。

        Returns:
            每个数据集对应一个 GapAnalysis 对象
        """
        results = []
        for dataset in datasets:
            ga = self._analyze_dataset(papers, dataset, metrics, domain)
            results.append(ga)
        return results

    def _analyze_dataset(
        self,
        papers: list[PaperRecord],
        dataset: str,
        metrics: list[str],
        domain: str,
    ) -> GapAnalysis:
        from agents.agent2_gap.ranker import METRIC_DIRECTION

        ga = GapAnalysis(
            domain=domain,
            as_of_year=2025,
            dataset=dataset,
        )

        # 按年份聚合各指标的最优值
        yearly_best: dict[int, dict[str, float]] = defaultdict(dict)
        all_values:  dict[str, list[float]]       = defaultdict(list)

        for paper in papers:
            if not paper.year or not paper.scores:
                continue
            if dataset not in paper.scores:
                continue
            score_obj = paper.scores[dataset]
            for metric in metrics:
                value = getattr(score_obj, metric, None)
                if value is None:
                    continue
                all_values[metric].append(value)
                is_higher_better = METRIC_DIRECTION.get(metric, True)
                current_best = yearly_best[paper.year].get(metric)
                if current_best is None:
                    yearly_best[paper.year][metric] = value
                elif is_higher_better and value > current_best:
                    yearly_best[paper.year][metric] = value
                elif not is_higher_better and value < current_best:
                    yearly_best[paper.year][metric] = value

        ga.yearly_sota = {int(y): v for y, v in yearly_best.items()}

        # 计算年度进步量（相邻年份 SOTA 的差值）
        sorted_years = sorted(yearly_best.keys())
        for i in range(1, len(sorted_years)):
            prev_year = sorted_years[i - 1]
            curr_year = sorted_years[i]
            delta = {}
            for metric in metrics:
                prev_val = yearly_best[prev_year].get(metric)
                curr_val = yearly_best[curr_year].get(metric)
                if prev_val is not None and curr_val is not None:
                    is_higher_better = METRIC_DIRECTION.get(metric, True)
                    raw_delta = curr_val - prev_val
                    delta[metric] = round(
                        raw_delta if is_higher_better else -raw_delta, 4
                    )
            if delta:
                ga.yearly_delta[int(curr_year)] = delta

        # 饱和度评估（基于最近 3 年平均进步量）
        for metric in metrics:
            recent_deltas = []
            for yr in sorted(ga.yearly_delta.keys())[-3:]:
                d = ga.yearly_delta[yr].get(metric)
                if d is not None:
                    recent_deltas.append(d)

            if not recent_deltas:
                ga.saturation[metric] = "insufficient_data"
                continue

            avg_delta = sum(recent_deltas) / len(recent_deltas)
            if avg_delta < 0.002:
                ga.saturation[metric] = "saturating"   # 年均进步 < 0.2%
            elif avg_delta < 0.008:
                ga.saturation[metric] = "active"        # 0.2%-0.8%
            else:
                ga.saturation[metric] = "rapid"         # > 0.8%

        # 当前方法间差距（最强 vs 最弱）
        for metric in metrics:
            vals = all_values[metric]
            if len(vals) >= 2:
                is_higher_better = METRIC_DIRECTION.get(metric, True)
                best  = max(vals) if is_higher_better else min(vals)
                worst = min(vals) if is_higher_better else max(vals)
                ga.current_range[metric] = round(abs(best - worst), 4)

        return ga
