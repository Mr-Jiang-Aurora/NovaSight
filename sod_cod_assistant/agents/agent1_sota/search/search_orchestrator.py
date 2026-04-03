"""
Agent1 搜索层 - 搜索调度器
并行调度四路搜索（S2/OpenAlex/DBLP/CVF），
合并结果并调用去重器，输出最终论文列表。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List

from config.knowledge_base import (
    get_domain_info, is_target_venue,
    get_venue_tier, get_standard_venue_name, get_venue_info,
)
from config.settings import settings as _global_settings
from shared.models import PaperRecord, PaperSource, SearchResult
from .semantic_scholar import SemanticScholarSearcher
from .openalex import OpenAlexSearcher
from .dblp import DBLPSearcher
from .cvf_open_access import CVFSearcher
from .deduplicator import PaperDeduplicator

logger = logging.getLogger(__name__)


def filter_by_venue_tier(
    papers: list,
    cfg=None,
    min_tier: int = None,
) -> list:
    """
    按 Venue Tier 过滤论文，同时标准化 venue 名称并回填 ccf_rank/sci_tier。

    Args:
        papers:   论文列表
        cfg:      配置对象（读取 VENUE_MIN_TIER），为 None 时使用全局 settings
        min_tier: 最低 Tier 要求（None 时从 cfg 读取）
                  1 = 只保留 CCF-A/Q1
                  2 = 同时保留 CCF-B/Q2

    Returns:
        过滤后的论文列表
    """
    if cfg is None:
        cfg = _global_settings
    if min_tier is None:
        min_tier = getattr(cfg, "VENUE_MIN_TIER", 1)

    result = []
    tier_stats: dict[int, int] = {0: 0, 1: 0, 2: 0}

    for paper in papers:
        # 先标准化 venue 名称，并回填缺失的 ccf_rank/sci_tier/impact_factor
        if paper.venue:
            std_venue = get_standard_venue_name(paper.venue)
            if std_venue not in ("Unknown", "BLACKLISTED"):
                paper.venue = std_venue
                info = get_venue_info(std_venue)
                if not paper.ccf_rank:
                    paper.ccf_rank = info.get("ccf_rank")
                if not paper.sci_tier:
                    paper.sci_tier = info.get("sci_tier")
                if paper.impact_factor is None:
                    paper.impact_factor = info.get("impact_factor")

        tier = get_venue_tier(paper.venue or "")
        tier_stats[tier] = tier_stats.get(tier, 0) + 1
        if tier >= min_tier:
            result.append(paper)

    logger.info(
        f"Venue Tier 过滤（min_tier={min_tier}）："
        f"Tier1={tier_stats.get(1, 0)} 篇，"
        f"Tier2={tier_stats.get(2, 0)} 篇，"
        f"过滤掉={tier_stats.get(0, 0)} 篇"
    )
    return result


class SearchOrchestrator:
    """
    搜索层调度器。
    并行启动四路搜索器，合并结果，调用去重器，过滤非目标期刊论文。
    单路搜索失败不影响其他路（失败返回空结果，errors 字段记录原因）。
    """

    def __init__(self) -> None:
        self._deduplicator = PaperDeduplicator()

    async def run_search(
        self,
        domain: str,
        target_venues: list[str] | None = None,
    ) -> List[PaperRecord]:
        """
        执行完整的四源并行搜索流程。

        步骤：
          1. 验证 domain 合法性（由 get_domain_info 抛出异常）
          2. 并行启动四路搜索器（asyncio.gather，单路失败不中断）
          3. 打印每路搜索的结果数量
          4. 合并所有论文，调用去重器
          5. 过滤非目标期刊的论文（二次保险）
          6. （可选）target_venues 过滤：只保留指定 venue 的论文
          7. 返回最终列表

        Args:
            domain:        研究方向，如 "COD"、"SOD"（大小写不敏感）
            target_venues: 增量模式下只搜索的 venue 列表；
                           None 表示全量搜索（默认行为）

        Returns:
            去重后的 PaperRecord 列表

        Raises:
            ValueError: 不支持的研究方向
        """
        # 验证 domain（会在不支持时抛出 ValueError）
        domain_info = get_domain_info(domain)
        logger.info(
            f"[Orchestrator] 开始搜索：{domain_info['full_name']} ({domain.upper()})"
        )

        start_time = time.monotonic()

        # ── 并行启动四路搜索 ───────────────────────────────────────────
        s2_searcher   = SemanticScholarSearcher()
        oa_searcher   = OpenAlexSearcher()
        dblp_searcher = DBLPSearcher()
        cvf_searcher  = CVFSearcher()

        # return_exceptions=True 保证单路失败不中断整体搜索
        results = await asyncio.gather(
            self._safe_search(s2_searcher,   domain, "Semantic Scholar"),
            self._safe_search(oa_searcher,   domain, "OpenAlex"),
            self._safe_search(dblp_searcher, domain, "DBLP"),
            self._safe_search(cvf_searcher,  domain, "CVF Open Access"),
            return_exceptions=False,
        )

        # ── 关闭所有 Session ──────────────────────────────────────────
        await asyncio.gather(
            s2_searcher.close(),
            oa_searcher.close(),
            dblp_searcher.close(),
            cvf_searcher.close(),
            return_exceptions=True,
        )

        # ── 打印每路结果并合并 ────────────────────────────────────────
        s2_result, oa_result, dblp_result, cvf_result = results

        source_labels = [
            ("Semantic Scholar", s2_result),
            ("OpenAlex",         oa_result),
            ("DBLP",             dblp_result),
            ("CVF Open Access",  cvf_result),
        ]

        all_papers: List[PaperRecord] = []
        for label, result in source_labels:
            count = len(result.papers) if result else 0
            err_count = len(result.errors) if result else 0
            status = "[OK]" if (result and not result.errors) else ("[W]" if result else "[X]")
            print(
                f"  {status} {label:20s}: 找到 {count:3d} 篇论文"
                + (f"({err_count} 个错误)" if err_count else "")
            )
            if result:
                all_papers.extend(result.papers)

        print(f"\n  [Merge] 四源合并前总计：{len(all_papers)} 条（含重复）")

        # ── 去重合并 ──────────────────────────────────────────────────
        deduped = self._deduplicator.deduplicate(all_papers)

        # ── 第一步：年份过滤 ─────────────────────────────────────────
        min_year = getattr(_global_settings, "SEARCH_MIN_YEAR", 2024)
        before_year = len(deduped)
        year_filtered = [
            p for p in deduped
            if p.year is None or p.year >= min_year
        ]
        removed_year = before_year - len(year_filtered)
        logger.info(
            f"年份过滤（>= {min_year}）："
            f"{before_year} 篇 → {len(year_filtered)} 篇"
            f"（过滤掉 {removed_year} 篇）"
        )

        # ── 第二步：Venue Tier 过滤 + 标准化 venue 名称 ──────────────
        final_papers = filter_by_venue_tier(year_filtered)
        logger.info(f"Venue Tier 过滤后剩余：{len(final_papers)} 篇")

        # ── 第三步（增量模式）：target_venues 过滤 ───────────────────
        if target_venues is not None:
            before_tv = len(final_papers)
            final_papers = [
                p for p in final_papers
                if any(
                    tv.lower() in (p.venue or "").lower()
                    for tv in target_venues
                )
            ]
            logger.info(
                f"Target venue 过滤：{before_tv} 篇 → {len(final_papers)} 篇"
            )

        elapsed = time.monotonic() - start_time
        print(
            f"  [Done] 去重后：{len(deduped)} 篇 → 年份+Tier 过滤后：{len(final_papers)} 篇，"
            f"总耗时 {elapsed:.1f}s\n"
        )
        logger.info(
            f"[Orchestrator] 搜索完成：{len(final_papers)} 篇，耗时 {elapsed:.1f}s"
        )

        return final_papers

    @staticmethod
    async def _safe_search(
        searcher: "BaseSearcher",
        domain: str,
        source_name: str,
        timeout_seconds: int = 180,
    ) -> SearchResult:
        """
        安全地执行单路搜索，捕获所有异常，并附加总超时保护。
        单路超时或失败均不影响其他路继续运行。

        Args:
            searcher:        搜索器实例
            domain:          研究方向
            source_name:     来源名称（用于日志）
            timeout_seconds: 单路搜索最长允许时间（默认 180 秒）

        Returns:
            SearchResult（失败/超时时 papers=[]，errors 记录原因）
        """
        from shared.models import PaperSource

        source_map = {
            "Semantic Scholar": PaperSource.SEMANTIC_SCHOLAR,
            "OpenAlex":         PaperSource.OPENALEX,
            "DBLP":             PaperSource.DBLP,
            "CVF Open Access":  PaperSource.CVF_OPEN_ACCESS,
        }
        source_enum = source_map.get(source_name, PaperSource.MANUAL)

        try:
            # 用 asyncio.wait_for 为每路搜索加上硬性时间上限
            return await asyncio.wait_for(
                searcher.search(domain),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"[Orchestrator] {source_name} 超过 {timeout_seconds}s 超时，"
                f"已中止并继续其他来源"
            )
            return SearchResult(
                source=source_enum,
                domain=domain,
                query_used="",
                papers=[],
                total_found=0,
                errors=[f"{source_name} 超时（>{timeout_seconds}s）"],
            )
        except Exception as e:
            logger.error(
                f"[Orchestrator] {source_name} 搜索失败（已捕获，不影响其他路）: {e}",
                exc_info=True,
            )
            return SearchResult(
                source=source_enum,
                domain=domain,
                query_used="",
                papers=[],
                total_found=0,
                errors=[f"{source_name} 搜索异常: {str(e)}"],
            )
