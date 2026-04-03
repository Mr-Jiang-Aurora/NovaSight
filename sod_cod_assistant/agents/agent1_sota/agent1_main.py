"""
Agent1 - SOTA 调研 Agent 主入口
Phase 4 实现：增量缓存层（最外层）+ 手动分数导入 + Phase 1-3 完整管线
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config.knowledge_base import get_domain_info, MONITORED_VENUES
from config.settings import settings
from shared.models import PaperRecord, SOTALeaderboard
from shared.utils import setup_logging, get_timestamp
from agents.agent1_sota.search import SearchOrchestrator

logger = logging.getLogger(__name__)


class Agent1SOTAAgent:
    """
    SOTA 调研 Agent - Phase 4 实现（含增量缓存层）。

    执行逻辑：
        有缓存 + 无新论文 → 直接返回缓存（秒级响应）
        有缓存 + 有新论文 → 只对有更新的 venue 重新 Phase1-3
        无缓存 / force_full → 全量运行 Phase 1-3
        → 合并手动分数 → 保存缓存 → 更新 index.json
    """

    def __init__(self) -> None:
        self._orchestrator = SearchOrchestrator()
        self._cache_dir = Path(settings.CACHE_DIR)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        domain: str,
        save_cache: bool = True,
        cache_filename: Optional[str] = None,
        skip_fetch: bool = False,
        skip_parse: bool = False,
        force_full: bool = False,
    ) -> List[PaperRecord]:
        """
        Agent1 完整入口（含增量缓存逻辑）。

        Args:
            domain:         研究方向，如 "COD"、"SOD"（大小写不敏感）
            save_cache:     是否将结果保存到增量缓存（CacheManager）
            cache_filename: （兼容旧接口）自定义旧格式缓存文件名，不影响新缓存
            skip_fetch:     True 时跳过 Phase 2（PDF 获取）
            skip_parse:     True 时跳过 Phase 3（表格解析）
            force_full:     True 时强制全量重跑（忽略现有缓存）

        Returns:
            处理后的 PaperRecord 列表

        Raises:
            ValueError: 不支持的研究方向
        """
        from agents.agent1_sota.cache.cache_manager import CacheManager
        from agents.agent1_sota.cache.increment_checker import IncrementChecker
        from agents.agent1_sota.cache.manual_scores_loader import ManualScoresLoader

        domain_info  = get_domain_info(domain)
        domain_upper = domain.upper()

        logger.info(f"[Agent1] 启动 SOTA 调研：{domain_info['chinese_name']} ({domain_upper})")
        print(f"\n{'='*60}")
        print(f"[Agent1] SOTA 调研 - {domain_info['full_name']}")
        print(f"{'='*60}")

        cache_mgr = CacheManager(settings.CACHE_DIR)
        checker   = IncrementChecker(cache_mgr)

        # ── 增量缓存检查 ───────────────────────────────────────────────
        target_venues  = None
        existing_papers: List[PaperRecord] = []

        if not force_full and cache_mgr.has_cache(domain_upper):
            logger.info(f"[Agent1] 发现 {domain_upper} 缓存，检查是否有新论文...")
            print(f"\n[Cache] 发现现有缓存，增量检测中...")
            update_map = checker.check_for_updates(domain_upper)
            venues_with_updates = [v for v, has_new in update_map.items() if has_new]

            if not venues_with_updates:
                print("[Cache] 无新论文，直接返回缓存（秒级响应）")
                logger.info("[Agent1] 无新论文，直接返回缓存")
                cached_papers = cache_mgr.load_cache(domain_upper) or []

                manual_path = str(Path(settings.CACHE_DIR).parent / "manual_scores.json")
                loader = ManualScoresLoader(manual_path)
                cached_papers, merge_stats = loader.load_and_merge(cached_papers, domain_upper)
                logger.info(f"手动分数合并（缓存路径）：{merge_stats}")

                self._print_summary(cached_papers, domain_info, None, None)
                return cached_papers

            logger.info(
                f"[Agent1] 发现 {len(venues_with_updates)} 个 venue 有新内容："
                f"{venues_with_updates}"
            )
            print(f"[Cache] {len(venues_with_updates)} 个 venue 有新内容，增量更新...")
            existing_papers = cache_mgr.load_cache(domain_upper) or []
            target_venues   = venues_with_updates
        else:
            reason = "强制全量" if force_full else "无缓存"
            logger.info(f"[Agent1] {reason}，开始完整流程...")
            print(f"\n[Cache] {reason}，执行完整流程...")

        venues_processed = target_venues or list(MONITORED_VENUES.keys())

        # ── Phase 1：搜索层 ────────────────────────────────────────────
        print("\n[Phase1] 搜索层（四源并联）")
        print("-" * 40)
        papers = await self._orchestrator.run_search(
            domain, target_venues=target_venues
        )

        # ── 搜索全空保护：所有源超时/失败时，直接返回现有缓存，避免覆盖历史数据 ──
        if not papers and existing_papers:
            logger.warning(
                "[Agent1] Phase 1 搜索结果为空（可能全部网络超时），"
                "直接使用现有缓存，跳过 Phase2/3 及缓存写入"
            )
            print(
                "\n[!!] Phase 1 搜索全部超时/失败，返回现有缓存，不覆盖历史数据"
            )
            manual_path = str(Path(settings.CACHE_DIR).parent / "manual_scores.json")
            loader = ManualScoresLoader(manual_path)
            existing_papers, merge_stats = loader.load_and_merge(existing_papers, domain_upper)
            if merge_stats["matched"] or merge_stats["new_added"]:
                print(
                    f"\n[Manual] 手动导入：匹配 {merge_stats['matched']} 篇，"
                    f"新增 {merge_stats['new_added']} 篇"
                )
            self._print_summary(existing_papers, domain_info, None, None)
            return existing_papers

        # ── Phase 2：PDF 获取层 ────────────────────────────────────────
        fetch_stats = None
        if not skip_fetch and papers:
            print(f"\n[Phase2] PDF 获取层（五级瀑布流，共 {len(papers)} 篇）")
            print("-" * 40)
            from agents.agent1_sota.fetcher.pdf_fetcher import PDFFetcher
            fetcher = PDFFetcher(settings)
            papers, fetch_stats = await fetcher.fetch_all(
                papers,
                max_concurrent=getattr(settings, "FETCH_MAX_CONCURRENT", 5),
            )
            print(
                f"\n[Phase2] 完成：{fetch_stats.success}/{fetch_stats.total} 篇获取成功 "
                f"（{fetch_stats.success_rate:.1f}%）"
            )
        elif skip_fetch:
            print("\n[Phase2] 已跳过 PDF 获取（skip_fetch=True）")

        # ── Phase 3：表格解析层 ────────────────────────────────────────
        parse_report = None
        if not skip_parse and papers:
            print(f"\n[Phase3] 表格解析层（四级分级提取，共 {len(papers)} 篇）")
            print("-" * 40)
            from agents.agent1_sota.parser.table_extractor import TableExtractor
            from agents.agent1_sota.parser.report_generator import ReportGenerator
            from shared.models import SOTALeaderboard

            extractor = TableExtractor(settings)
            papers, parse_report = await extractor.extract_all(
                papers,
                domain_upper,
                max_concurrent=getattr(settings, "PARSE_MAX_CONCURRENT", 3),
            )
            scored_count = sum(1 for p in papers if p.scores)
            print(
                f"\n[Phase3] 完成：{scored_count}/{len(papers)} 篇成功提取分数，"
                f"失败 {parse_report.failure_count} 篇"
            )

            # 生成排行榜 + 失败报告输出文件
            generator = ReportGenerator()
            from config.settings import get_agent_output_dir
            output_dir = get_agent_output_dir(1)
            output_paths = generator.generate_all(
                SOTALeaderboard(
                    domain=domain_upper,
                    papers=papers,
                    total_papers=len(papers),
                    search_completed=True,
                    fetch_completed=not skip_fetch,
                    parse_completed=True,
                ),
                parse_report,
                output_dir=output_dir,
            )
            print(f"\n[Phase3] 输出文件：")
            for name, path in output_paths.items():
                print(f"  {name}: {path}")
        elif skip_parse:
            print("\n[Phase3] 已跳过表格解析（skip_parse=True）")

        # ── 合并到缓存 ────────────────────────────────────────────────
        all_papers = cache_mgr.merge_new_papers(domain_upper, existing_papers, papers)

        # ── 手动分数合并（Phase 3 之后执行）─────────────────────────
        manual_path = str(Path(settings.CACHE_DIR).parent / "manual_scores.json")
        loader = ManualScoresLoader(manual_path)
        all_papers, merge_stats = loader.load_and_merge(all_papers, domain_upper)
        logger.info(f"手动分数合并：{merge_stats}")
        if merge_stats["matched"] or merge_stats["new_added"]:
            print(
                f"\n[Manual] 手动导入：匹配 {merge_stats['matched']} 篇，"
                f"新增 {merge_stats['new_added']} 篇"
            )

        # ── 打印统计摘要 ──────────────────────────────────────────────
        self._print_summary(all_papers, domain_info, fetch_stats, parse_report)

        # ── 保存增量缓存 ──────────────────────────────────────────────
        if save_cache and all_papers:
            # 回退保护：若新结果比现有缓存少超过 30%，跳过写入（防止搜索失败时覆盖历史数据）
            prev_cached = cache_mgr.load_cache(domain_upper) or []
            if prev_cached and len(all_papers) < len(prev_cached) * 0.7:
                logger.warning(
                    f"[Agent1] 缓存回退保护触发：新结果 {len(all_papers)} 篇 < "
                    f"历史缓存 {len(prev_cached)} 篇的 70%，跳过覆写"
                )
                print(
                    f"\n[Cache] ⚠ 回退保护：新结果 ({len(all_papers)}) "
                    f"远少于历史缓存 ({len(prev_cached)})，不覆写缓存"
                )
            else:
                cache_mgr.save_cache(domain_upper, all_papers)
                checker.update_index(domain_upper, venues_processed)
                print(f"\n[Cache] 增量缓存已更新：{len(all_papers)} 篇")

            # 兼容旧格式：同时保存一份旧格式 JSON
            if not cache_filename:
                cache_filename = f"{domain_upper}_papers_{get_timestamp()}"
            cache_path = self._cache_dir / f"{cache_filename}.json"
            self._save_to_json(papers, cache_path, domain, fetch_stats)
            print(f"[Save] 旧格式缓存已保存：{cache_path}")

        # ── TASK4：生成论文信息卡片 MD ────────────────────────────────
        try:
            from agents.agent1_sota.paper_card_writer import PaperCardWriter
            from config.settings import get_agent_output_dir
            card_writer = PaperCardWriter()
            card_path   = card_writer.write(
                papers     = all_papers,
                domain     = domain_upper,
                output_dir = get_agent_output_dir(1),
            )
            print(f"[PaperCards] 论文信息卡片已生成：{card_path}")
        except Exception as e:
            logger.warning(f"[Agent1] 论文信息卡片生成失败（不影响主流程）：{e}")

        return all_papers

    # ── 搜索结果摘要打印 ───────────────────────────────────────────────

    def _print_summary(
        self,
        papers: List[PaperRecord],
        domain_info: dict,
        fetch_stats=None,
        parse_report=None,
    ) -> None:
        """打印搜索+获取+解析结果的统计摘要信息。"""
        if not papers:
            print("\n[!!] 未找到任何符合条件的论文，请检查 API Key 配置")
            return

        print(f"\n[Stats] 结果摘要")
        print("-" * 40)
        print(f"  总计论文数 : {len(papers)} 篇")

        # 按来源统计
        from collections import Counter
        from shared.models import PaperSource
        source_counter: Counter = Counter()
        for p in papers:
            for src in p.found_by:
                source_counter[src.value] += 1
        print("  来源分布   :")
        src_label_map = {
            PaperSource.SEMANTIC_SCHOLAR.value: "Semantic Scholar",
            PaperSource.OPENALEX.value:         "OpenAlex",
            PaperSource.DBLP.value:             "DBLP",
            PaperSource.CVF_OPEN_ACCESS.value:  "CVF Open Access",
        }
        for src_val, count in source_counter.most_common():
            label = src_label_map.get(src_val, src_val)
            print(f"    {label:20s}: {count} 篇")

        # 按期刊/会议统计
        from collections import Counter as C2
        venue_counter: C2 = C2(p.venue for p in papers if p.venue)
        print("  期刊/会议  :")
        for venue, count in venue_counter.most_common(8):
            print(f"    {venue:20s}: {count} 篇")

        # 按年份统计
        year_counter: C2 = C2(p.year for p in papers if p.year)
        if year_counter:
            years_str = "  ".join(
                f"{y}:{c}" for y, c in sorted(year_counter.items())
            )
            print(f"  年份分布   : {years_str}")

        # PDF 统计
        has_pdf   = sum(1 for p in papers if p.pdf_url)
        has_arxiv = sum(1 for p in papers if p.arxiv_id)
        print(f"  有 PDF 链接: {has_pdf} 篇 / 有 arXiv ID: {has_arxiv} 篇")

        # PDF 获取层统计
        if fetch_stats:
            print(f"  PDF 获取率 : {fetch_stats.success}/{fetch_stats.total} "
                  f"（{fetch_stats.success_rate:.1f}%）")
            if fetch_stats.by_source:
                print(f"  PDF 来源   : {fetch_stats.by_source}")

        # 表格解析层统计
        if parse_report:
            scored = sum(1 for p in papers if p.scores)
            print(f"  分数提取   : {scored}/{len(papers)} 篇成功，"
                  f"{parse_report.failure_count} 篇失败")

    # ── JSON 序列化保存 ────────────────────────────────────────────────

    def _save_to_json(
        self,
        papers: List[PaperRecord],
        path: Path,
        domain: str,
        fetch_stats=None,
    ) -> None:
        """
        将论文列表序列化为 JSON 文件（使用 Pydantic model_dump）。
        同时写入元数据（生成时间、领域、总数、PDF 统计）。
        """
        fetch_meta: dict = {}
        if fetch_stats:
            fetch_meta = {
                "fetch_success": fetch_stats.success,
                "fetch_total":   fetch_stats.total,
                "fetch_rate":    f"{fetch_stats.success_rate:.1f}%",
                "fetch_by_source": fetch_stats.by_source,
            }
        output = {
            "metadata": {
                "domain": domain.upper(),
                "generated_at": datetime.now().isoformat(),
                "phase": "Phase2-FetchLayer",
                "total_papers": len(papers),
                "version": "2.0",
                **fetch_meta,
            },
            "papers": [p.model_dump(mode="json") for p in papers],
        }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"[Agent1] 已保存 {len(papers)} 篇论文到：{path}")
        except IOError as e:
            logger.error(f"[Agent1] 保存 JSON 失败: {e}")

    # ── 从缓存加载（供后续 Phase 使用）───────────────────────────────

    def load_from_cache(self, cache_path: str) -> List[PaperRecord]:
        """
        从 JSON 缓存文件加载论文列表。

        Args:
            cache_path: 缓存文件路径（相对或绝对路径）

        Returns:
            PaperRecord 列表

        Raises:
            FileNotFoundError: 缓存文件不存在
        """
        path = Path(cache_path)
        if not path.exists():
            raise FileNotFoundError(f"缓存文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        papers_data = data.get("papers", [])
        papers = [PaperRecord.model_validate(p) for p in papers_data]
        logger.info(f"[Agent1] 从缓存加载 {len(papers)} 篇论文")
        return papers

    # ── 同步封装（供非 async 环境调用）──────────────────────────────

    def run_sync(
        self,
        domain: str,
        save_cache: bool = True,
        cache_filename: Optional[str] = None,
        skip_fetch: bool = False,
        skip_parse: bool = False,
        force_full: bool = False,
    ) -> List[PaperRecord]:
        """
        同步版本入口（内部调用 asyncio.run）。
        适用于脚本、Jupyter Notebook 等非 async 环境。
        """
        return asyncio.run(
            self.run(
                domain,
                save_cache=save_cache,
                cache_filename=cache_filename,
                skip_fetch=skip_fetch,
                skip_parse=skip_parse,
                force_full=force_full,
            )
        )
