"""
Agent1 搜索层 - DBLP 搜索器
通过 DBLP 搜索 API 按期刊/会议 stream 遍历，
无需任何认证，直接使用公开接口。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from config.knowledge_base import (
    get_domain_info, is_target_venue, MONITORED_VENUES
)
from config.settings import settings
from shared.models import PaperRecord, PaperSource, SearchResult
from shared.utils import extract_arxiv_id, normalize_doi, clean_author_name
from .base_searcher import BaseSearcher

logger = logging.getLogger(__name__)

# DBLP 搜索 API 基础 URL
DBLP_SEARCH_URL = "https://dblp.org/search/publ/api"

# DBLP 速率限制：官方建议请求间隔 >= 2 秒
DBLP_REQUEST_DELAY = 2.0


class DBLPSearcher(BaseSearcher):
    """
    DBLP 搜索器。
    使用 DBLP stream 查询按期刊/会议筛选论文，再按领域关键词过滤。
    DBLP 不需要任何 API Key，但需要遵守 2 秒请求间隔。
    """

    SOURCE_NAME = "DBLP"
    MAX_RETRIES = 2       # DBLP 偶发 500/503，重试 2 次即可，避免无限阻塞
    BACKOFF_BASE = 1.5    # 覆盖基类的退避基数，DBLP 1.5^n 秒（1.5s, 2.25s）

    def __init__(self) -> None:
        super().__init__()
        # 覆盖基类速率限制为 2 秒
        self._dblp_delay = DBLP_REQUEST_DELAY

    async def _rate_limit(self) -> None:
        """DBLP 速率限制：2 秒间隔。"""
        import time as _time
        elapsed = _time.monotonic() - self._last_request_time
        if elapsed < self._dblp_delay:
            await asyncio.sleep(self._dblp_delay - elapsed)

    # ── 主入口 ────────────────────────────────────────────────────────

    async def search(self, domain: str) -> SearchResult:
        """
        遍历所有 search_in_dblp=True 的目标期刊/会议，
        对每个来源用领域关键词搜索，合并结果。
        """
        start_time = time.monotonic()
        domain_info = get_domain_info(domain)
        all_papers: List[PaperRecord] = []
        errors: List[str] = []

        # 获取需要搜索 DBLP 的目标来源列表
        dblp_venues = {
            name: info
            for name, info in MONITORED_VENUES.items()
            if info.get("search_in_dblp", False)
        }

        for venue_name, venue_info in dblp_venues.items():
            for query in domain_info["search_queries"]:
                try:
                    papers = await self.search_by_venue_and_keyword(
                        venue_name=venue_name,
                        venue_info=venue_info,
                        keyword=query,
                    )
                    if papers:
                        logger.info(
                            f"[DBLP] {venue_name} × '{query}' → {len(papers)} 篇"
                        )
                    all_papers.extend(papers)
                except Exception as e:
                    err_msg = f"DBLP搜索失败 [{venue_name}×'{query}']: {e}"
                    logger.warning(f"[DBLP] {err_msg}")
                    errors.append(err_msg)

        # 简单去重（按 doi 或 title）
        seen: set[str] = set()
        unique_papers: List[PaperRecord] = []
        for p in all_papers:
            key = p.doi or p.arxiv_id or p.title
            if key and key not in seen:
                seen.add(key)
                unique_papers.append(p)

        elapsed = time.monotonic() - start_time
        logger.info(
            f"[DBLP] 搜索完成：共 {len(unique_papers)} 篇，耗时 {elapsed:.1f}s"
        )

        return SearchResult(
            source=PaperSource.DBLP,
            domain=domain,
            query_used="; ".join(domain_info["search_queries"]),
            papers=unique_papers,
            total_found=len(unique_papers),
            search_time_seconds=elapsed,
            errors=errors,
        )

    # ── 核心搜索方法 ──────────────────────────────────────────────────

    async def search_by_venue_and_keyword(
        self,
        venue_name: str,
        venue_info: Dict[str, Any],
        keyword: str,
        max_results: int = 100,
    ) -> List[PaperRecord]:
        """
        使用 DBLP stream 查询语法，在指定期刊/会议内搜索关键词。

        DBLP stream 查询格式（注意末尾冒号不能省略）：
          期刊：stream:streams/journals/pami:
          会议：stream:streams/conf/cvpr:

        Args:
            venue_name:  标准期刊/会议名（如 "CVPR"、"IEEE TPAMI"）
            venue_info:  知识库中的期刊/会议信息字典
            keyword:     领域搜索关键词
            max_results: 最多返回条数（DBLP 单次最多 1000，建议 100）

        Returns:
            PaperRecord 列表
        """
        dblp_key = venue_info.get("dblp_key", "")
        if not dblp_key:
            logger.debug(f"[DBLP] {venue_name} 无 dblp_key，跳过")
            return []

        # 构建 stream 查询字符串（类型 journals 或 conf）
        venue_type = "journals" if venue_info.get("type") == "journal" else "conf"
        # dblp_key 格式：journals/pami 或 conf/cvpr，取最后一部分
        dblp_venue_id = dblp_key.split("/")[-1]
        stream_query = (
            f"{keyword} "
            f"stream:streams/{venue_type}/{dblp_venue_id}:"
        )

        params = {
            "q": stream_query,
            "format": "json",
            "h": min(max_results, 1000),  # h 参数控制返回数量
            "f": 0,                        # 起始偏移（分页用）
        }

        data = await self._make_request(DBLP_SEARCH_URL, params=params)
        if not data:
            return []

        # DBLP JSON 响应结构：result.hits.hit[]
        try:
            hits = data["result"]["hits"].get("hit", [])
        except (KeyError, TypeError):
            logger.debug(f"[DBLP] {venue_name} 响应格式异常: {str(data)[:200]}")
            return []

        if not hits:
            return []

        papers: List[PaperRecord] = []
        for hit in hits:
            paper = self._parse_hit(hit, venue_name, venue_info)
            if paper is not None:
                papers.append(paper)

        return papers

    # ── 数据解析 ──────────────────────────────────────────────────────

    def _parse_hit(
        self,
        hit: Dict[str, Any],
        venue_name: str,
        venue_info: Dict[str, Any],
    ) -> Optional[PaperRecord]:
        """
        将 DBLP API 的单条 hit 解析为 PaperRecord。

        DBLP hit 结构：
          { "@score": ..., "@id": ..., "info": { title, year, venue, url, doi, ... } }
        """
        info = hit.get("info", {})
        if not info:
            return None

        title = (info.get("title") or "").strip()
        # 去除 DBLP 标题中有时包含的尾部 "." 或 "CoRR"
        title = title.rstrip(".")
        if not title:
            return None

        # 年份
        year_raw = info.get("year")
        year: Optional[int] = None
        try:
            year = int(year_raw) if year_raw else None
        except (ValueError, TypeError):
            pass

        # 过滤 2019 年以前的论文
        if year and year < 2019:
            return None

        # 来源过滤（排除 CoRR 即 arXiv 预印本）
        dblp_venue = info.get("venue", "")
        if dblp_venue.lower() in ("corr", "arxiv"):
            return None

        # DOI
        doi = normalize_doi(info.get("doi", ""))

        # arXiv ID（DBLP 条目 URL 有时含 arXiv 链接）
        entry_url = info.get("url", "")
        arxiv_id = extract_arxiv_id(entry_url)

        # 论文 URL（DBLP 条目页面）
        paper_url = entry_url if entry_url else None

        # 作者（DBLP 的 authors 字段可能是 list 或 dict）
        authors_raw = info.get("authors", {})
        authors = self._extract_authors(authors_raw)

        return PaperRecord(
            paper_id="",
            arxiv_id=arxiv_id,
            doi=doi,
            title=title,
            authors=authors,
            year=year,
            venue=venue_name,
            venue_full=venue_info.get("full_name"),
            ccf_rank=venue_info.get("ccf_rank"),
            sci_tier=venue_info.get("sci_tier"),
            impact_factor=venue_info.get("impact_factor"),
            paper_url=paper_url,
            found_by=[PaperSource.DBLP],
        )

    @staticmethod
    def _extract_authors(authors_raw: Any) -> List[str]:
        """
        从 DBLP authors 字段提取作者列表。
        DBLP 的 authors 字段格式不统一：
          - 单作者：{"author": "Name"} 或 {"author": {"text": "Name"}}
          - 多作者：{"author": ["Name1", "Name2"]} 或 [{"text": "Name"}, ...]
        """
        if not authors_raw:
            return []

        author_field = authors_raw.get("author", authors_raw)

        if isinstance(author_field, str):
            return [clean_author_name(author_field)]

        if isinstance(author_field, dict):
            name = author_field.get("text") or author_field.get("name", "")
            return [clean_author_name(name)] if name else []

        if isinstance(author_field, list):
            result = []
            for a in author_field:
                if isinstance(a, str):
                    result.append(clean_author_name(a))
                elif isinstance(a, dict):
                    name = a.get("text") or a.get("name", "")
                    if name:
                        result.append(clean_author_name(name))
            return result

        return []
