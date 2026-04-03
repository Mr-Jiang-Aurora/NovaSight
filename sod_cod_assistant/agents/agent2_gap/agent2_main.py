"""
Agent2 主入口：指标对比诊断
"""

import logging
from typing import TYPE_CHECKING

from shared.models import Agent2Report, SOTALeaderboard
from config.knowledge_base import DOMAIN_KNOWLEDGE_BASE

logger = logging.getLogger(__name__)


class Agent2:
    """指标对比诊断 Agent"""

    def __init__(self, settings):
        self.settings = settings

    async def run(
        self,
        leaderboard: SOTALeaderboard,
        domain: str,
        generate_narrative: bool = True,
        user_method_desc:   str  = "",
    ) -> Agent2Report:
        """
        Agent2 主入口。

        Args:
            leaderboard:        来自 Agent1 的排行榜数据
            domain:             研究领域（COD/SOD）
            generate_narrative: 是否调用 Claude API 生成自然语言报告
            user_method_desc:   用户当前研究方案描述（可选，主控 Agent 传入）

        Returns:
            Agent2Report 完整诊断报告
        """
        from agents.agent2_gap.ranker              import Ranker
        from agents.agent2_gap.gap_analyzer        import GapAnalyzer
        from agents.agent2_gap.profiler            import Profiler
        from agents.agent2_gap.scorer              import Scorer
        from agents.agent2_gap.narrative_generator import NarrativeGenerator
        from agents.agent2_gap.report_writer       import ReportWriter

        domain_upper = domain.upper()
        domain_info  = DOMAIN_KNOWLEDGE_BASE.get(domain_upper, {})
        datasets     = domain_info.get("datasets", ["COD10K", "CAMO", "NC4K"])
        metrics      = domain_info.get("metrics",  ["Sm", "Em", "Fm", "MAE"])

        papers = leaderboard.papers
        logger.info(
            f"[Agent2] 开始诊断：{domain_upper}，"
            f"{len(papers)} 篇论文，"
            f"{sum(1 for p in papers if p.scores)} 篇有分数"
        )

        report = Agent2Report(
            domain=domain_upper,
            total_methods=len(papers),
            scored_methods=sum(1 for p in papers if p.scores),
        )

        # ── 1. 多维度排行榜 ──────────────────────────────────────────
        ranker = Ranker()
        report.rankings = ranker.compute_all_rankings(
            papers, datasets, metrics
        )
        logger.info(f"[Agent2] 排行榜计算完成：{len(report.rankings)} 个")

        # ── 2. 差距与进步率分析 ───────────────────────────────────────
        analyzer = GapAnalyzer()
        report.gap_analyses = analyzer.analyze(papers, datasets, metrics, domain_upper)
        logger.info(f"[Agent2] 差距分析完成：{len(report.gap_analyses)} 个数据集")

        # ── 3. 综合得分计算 ───────────────────────────────────────────
        scorer = Scorer(datasets=datasets)
        ranked = scorer.rank_all(papers)
        logger.info(f"[Agent2] 综合得分计算完成：{len(ranked)} 篇")

        # ── 4. 方法强弱画像 ───────────────────────────────────────────
        profiler = Profiler()
        report.profiles = profiler.profile_all(papers, report.rankings, scorer)
        logger.info(f"[Agent2] 方法画像完成：{len(report.profiles)} 篇")

        # ── 5. 自然语言报告 ───────────────────────────────────────────
        if generate_narrative:
            import asyncio
            narrator = NarrativeGenerator(self.settings)
            if not user_method_desc:
                user_method_desc = getattr(self.settings, "USER_METHOD_DESC", "")
            # 用 asyncio.to_thread 避免阻塞 FastAPI 事件循环
            report.narrative = await asyncio.to_thread(
                narrator.generate,
                report,
                domain_upper,
                user_method_desc=user_method_desc,
                max_retries=2,
            )
            report.summary = report.narrative[:300] + "..." if report.narrative else ""
            logger.info("[Agent2] 自然语言报告生成完成")

        # ── 6. 输出文件 ───────────────────────────────────────────────
        writer = ReportWriter()
        from config.settings import get_agent_output_dir
        output_paths = writer.write_all(report, get_agent_output_dir(2))
        logger.info(f"[Agent2] 输出文件：{output_paths}")

        return report
