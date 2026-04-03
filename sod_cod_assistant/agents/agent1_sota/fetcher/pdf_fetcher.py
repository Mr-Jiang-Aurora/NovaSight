"""
Agent1 - 第二层：PDF 获取层主入口
五级优先级瀑布流，命中即停止。

优先级顺序：
  1. S2 openAccessPdf 字段（搜索时已填充，直接使用，0 网络请求）
  2. arXiv 直链（无 Key，~70-80% 覆盖）
  3. CVF/NeurIPS 开放库（无 Key，顶会 ~100%）
  4. Unpaywall（需邮箱，期刊论文主力）
  5. CORE（需 Key，可选兜底）
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from shared.models import PaperRecord

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """单篇论文 PDF 获取结果"""
    paper_id: str
    pdf_url:  Optional[str]
    # 来源标识：s2 / arxiv / conference / unpaywall / core / none
    source:   str
    success:  bool


@dataclass
class FetchStats:
    """批量获取的统计信息"""
    total:       int = 0
    already_had: int = 0   # 搜索层已有 pdf_url 的论文数
    attempted:   int = 0   # 实际需要获取的论文数
    success:     int = 0   # 成功获取（含 already_had）
    failed:      int = 0
    by_source:   dict = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """总成功率（含已有 URL）"""
        return self.success / self.total * 100 if self.total else 0.0

    @property
    def fetch_rate(self) -> float:
        """新获取成功率（不含已有 URL）"""
        if self.attempted == 0:
            return 100.0
        return (self.success - self.already_had) / self.attempted * 100


class PDFFetcher:
    """
    PDF 获取层主入口。
    负责实例化四个子获取器，并按优先级瀑布流为每篇论文找到最优 PDF 链接。
    """

    def __init__(self, settings) -> None:
        from .arxiv_fetcher      import ArXivFetcher
        from .conference_fetcher import ConferenceFetcher
        from .unpaywall_fetcher  import UnpywallFetcher
        from .core_fetcher       import COREFetcher

        self.arxiv_fetcher     = ArXivFetcher()
        self.conf_fetcher      = ConferenceFetcher()
        self.unpaywall_fetcher = UnpywallFetcher(
            email=settings.UNPAYWALL_EMAIL
        )
        self.core_fetcher      = COREFetcher(
            api_key=getattr(settings, "CORE_API_KEY", None) or None
        )

    async def fetch_one(self, paper: "PaperRecord") -> FetchResult:
        """
        对单篇论文执行五级瀑布流，命中即停止。
        返回 FetchResult，其中 success=True 表示找到了 PDF 链接。
        """
        pid = paper.paper_id or paper.title[:40]

        # 优先级 1：S2 已提供直链（最快，0 网络请求）
        if paper.pdf_url:
            return FetchResult(pid, paper.pdf_url, "s2", True)

        # 优先级 2：arXiv 直链
        url = await self.arxiv_fetcher.get_pdf_url(paper)
        if url:
            return FetchResult(pid, url, "arxiv", True)

        # 优先级 3：顶会开放库（CVF/NeurIPS）
        url = await self.conf_fetcher.get_pdf_url(paper)
        if url:
            return FetchResult(pid, url, "conference", True)

        # 优先级 4：Unpaywall（期刊 DOI）
        url = await self.unpaywall_fetcher.get_pdf_url(paper)
        if url:
            return FetchResult(pid, url, "unpaywall", True)

        # 优先级 5：CORE 兜底
        url = await self.core_fetcher.get_pdf_url(paper)
        if url:
            return FetchResult(pid, url, "core", True)

        logger.warning(f"[PDF] 所有渠道均失败：{paper.title[:60]}")
        return FetchResult(pid, None, "none", False)

    async def fetch_all(
        self,
        papers: list["PaperRecord"],
        max_concurrent: int = 5,
    ) -> tuple[list["PaperRecord"], FetchStats]:
        """
        并发批量获取所有论文的 PDF URL。
        成功时更新 paper.pdf_url 和 paper.pdf_fetched 字段。

        Args:
            papers:         论文列表
            max_concurrent: 最大并发数（默认 5，避免对单一服务施压过大）

        Returns:
            (更新后的论文列表, 统计信息)
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_sem(paper: "PaperRecord") -> FetchResult:
            async with semaphore:
                result = await self.fetch_one(paper)
                if result.success:
                    paper.pdf_url    = result.pdf_url
                    paper.pdf_fetched = True
                return result

        already_have = [p for p in papers if p.pdf_url]
        need_fetch   = [p for p in papers if not p.pdf_url]

        logger.info(
            f"[PDF] 开始获取：共 {len(papers)} 篇，"
            f"已有 {len(already_have)} 篇，"
            f"待获取 {len(need_fetch)} 篇"
        )

        tasks   = [fetch_with_sem(p) for p in need_fetch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        stats = FetchStats(
            total=len(papers),
            already_had=len(already_have),
            attempted=len(need_fetch),
            success=len(already_have),  # 已有的先计入成功
            failed=0,
        )

        for r in results:
            if isinstance(r, Exception):
                stats.failed += 1
                logger.debug(f"[PDF] 获取异常（已捕获）: {r}")
                continue
            if r.success:
                stats.success += 1
                stats.by_source[r.source] = stats.by_source.get(r.source, 0) + 1
            else:
                stats.failed += 1

        logger.info(
            f"[PDF] 获取完成：{stats.success}/{stats.total} 篇 "
            f"（总成功率 {stats.success_rate:.1f}%，"
            f"新获取 {stats.fetch_rate:.1f}%）"
            f" | 来源分布：{stats.by_source}"
        )
        return papers, stats
