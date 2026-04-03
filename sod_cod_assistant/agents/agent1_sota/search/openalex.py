"""
Agent1 搜索层 - OpenAlex 搜索器
使用 OpenAlex 语义搜索 API，配合 cursor 分页，
支持 abstract_inverted_index 重构完整摘要。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from config.knowledge_base import get_domain_info, is_target_venue, MONITORED_VENUES
from config.settings import settings
from shared.models import PaperRecord, PaperSource, SearchResult
from shared.utils import extract_arxiv_id, normalize_doi, clean_author_name
from .base_searcher import BaseSearcher

logger = logging.getLogger(__name__)

# OpenAlex API 基础 URL
OA_BASE_URL = "https://api.openalex.org"

# 每页结果数量
PAGE_SIZE = 50
# 最多获取页数（避免无限分页，每页50条，最多取3页=150条）
MAX_PAGES = 3


class OpenAlexSearcher(BaseSearcher):
    """
    OpenAlex 搜索器。
    2026年2月起 OpenAlex 语义搜索需要 API Key。
    无 Key 时降级使用普通关键词搜索（search 参数）。
    """

    SOURCE_NAME = "OpenAlex"
    MAX_RETRIES = 3

    def __init__(self) -> None:
        super().__init__()
        self._api_key = settings.OPENALEX_API_KEY
        self._email = settings.OPENALEX_EMAIL

    def _build_params(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        构建基础请求参数，附加 API Key 和 email（polite pool）。
        OpenAlex 的认证通过 URL 参数而非 Header 传递。
        """
        params: Dict[str, Any] = {}
        if self._api_key:
            params["api_key"] = self._api_key
        elif self._email:
            # 无 Key 时用 email 进入 polite pool（更稳定的公共池）
            params["mailto"] = self._email
        if extra:
            params.update(extra)
        return params

    # ── 主入口 ────────────────────────────────────────────────────────

    async def search(self, domain: str) -> SearchResult:
        """
        执行 OpenAlex 搜索：对每个搜索查询语句执行语义搜索，合并结果。
        """
        start_time = time.monotonic()
        domain_info = get_domain_info(domain)
        all_papers: List[PaperRecord] = []
        errors: List[str] = []

        for query in domain_info["search_queries"]:
            try:
                papers = await self.search_semantic(query)
                logger.info(
                    f"[OpenAlex] 查询 '{query}' → {len(papers)} 篇（过滤后）"
                )
                all_papers.extend(papers)
            except Exception as e:
                err_msg = f"OpenAlex 搜索失败 '{query}': {e}"
                logger.warning(f"[OpenAlex] {err_msg}")
                errors.append(err_msg)
            # 查询之间加间隔
            await self._rate_limit()

        # 按 paper_id 简单去重
        seen: set[str] = set()
        unique_papers: List[PaperRecord] = []
        for p in all_papers:
            key = p.arxiv_id or p.doi or p.title
            if key and key not in seen:
                seen.add(key)
                unique_papers.append(p)

        elapsed = time.monotonic() - start_time
        return SearchResult(
            source=PaperSource.OPENALEX,
            domain=domain,
            query_used="; ".join(domain_info["search_queries"]),
            papers=unique_papers,
            total_found=len(unique_papers),
            search_time_seconds=elapsed,
            errors=errors,
        )

    # ── 语义搜索（核心方法）──────────────────────────────────────────

    async def search_semantic(
        self,
        query: str,
        min_year: int = 2019,
    ) -> List[PaperRecord]:
        """
        使用 OpenAlex 语义搜索（search.semantic 参数，需 API Key）。
        无 Key 时回退到普通关键词搜索（search 参数）。

        分页策略：使用 cursor pagination（cursor=* 起始），每页 50 条，最多 3 页。

        Args:
            query:    搜索查询字符串
            min_year: 最早发表年份过滤（filter=publication_year:>XXXX）

        Returns:
            过滤后的 PaperRecord 列表
        """
        all_papers: List[PaperRecord] = []
        cursor = "*"  # cursor pagination 起始值

        # 根据是否有 API Key 选择搜索模式
        search_key = "search.semantic" if self._api_key else "search"

        # 语义搜索不支持 cursor 分页，使用 page/per_page（最多 50 条/页）
        # 普通关键词搜索（search 参数）支持 cursor 分页
        use_cursor = (search_key != "search.semantic")
        cursor = "*"

        for page_num in range(1, MAX_PAGES + 1):
            if use_cursor:
                pagination = {"per-page": PAGE_SIZE, "cursor": cursor}
            else:
                # 语义搜索：page-based 分页，每页最多 50 条
                pagination = {"per-page": min(PAGE_SIZE, 50), "page": page_num}

            params = self._build_params({
                search_key: query,
                "filter": f"publication_year:>{min_year - 1}",
                **pagination,
                "select": (
                    "id,doi,title,display_name,publication_year,"
                    "primary_location,open_access,abstract_inverted_index,"
                    "authorships,cited_by_count,best_oa_location"
                ),
            })

            data = await self._make_request(f"{OA_BASE_URL}/works", params=params)
            if not data:
                break

            results = data.get("results", [])
            if not results:
                break

            for item in results:
                paper = self._parse_work_item(item)
                if paper is None:
                    continue
                if not is_target_venue(paper.venue or ""):
                    continue
                all_papers.append(paper)

            # cursor 分页：获取下一页 cursor
            if use_cursor:
                meta = data.get("meta", {})
                next_cursor = meta.get("next_cursor")
                if not next_cursor:
                    break
                cursor = next_cursor
            else:
                # page 分页：结果不足一页则已到末尾
                if len(results) < PAGE_SIZE:
                    break

            await self._rate_limit()

        return all_papers

    # ── 数据解析 ──────────────────────────────────────────────────────

    def _parse_work_item(self, item: Dict[str, Any]) -> Optional[PaperRecord]:
        """
        将 OpenAlex Works API 返回的单条数据解析为 PaperRecord。

        注意：OpenAlex 使用 display_name 作为标题，
        abstract_inverted_index 需要重构为普通文本。
        """
        # 标题（OpenAlex 用 display_name）
        title = (
            item.get("display_name")
            or item.get("title")
            or ""
        ).strip()
        if not title:
            return None

        # 年份
        year: Optional[int] = item.get("publication_year")

        # DOI 提取与规范化
        doi_raw = item.get("doi") or ""
        doi = normalize_doi(doi_raw)

        # arXiv ID（从 DOI 或 best_oa_location 中提取）
        arxiv_id: Optional[str] = None
        best_oa = item.get("best_oa_location") or {}
        oa_url = best_oa.get("url", "") or ""
        if "arxiv.org" in oa_url:
            arxiv_id = extract_arxiv_id(oa_url)
        if not arxiv_id and doi:
            arxiv_id = extract_arxiv_id(doi)

        # 作者列表（authorships 是包含 author 对象的列表）
        authorships = item.get("authorships") or []
        authors = [
            clean_author_name(a.get("author", {}).get("display_name", ""))
            for a in authorships
            if a.get("author", {}).get("display_name")
        ]

        # 来源期刊/会议（primary_location → source）
        primary_location = item.get("primary_location") or {}
        source_info = primary_location.get("source") or {}
        venue_raw = (source_info.get("display_name") or "").strip()
        venue_normalized = self._normalize_venue(venue_raw)
        venue_info = MONITORED_VENUES.get(venue_normalized, {})

        # 论文 URL（优先 arXiv，其次 DOI）
        paper_url: Optional[str] = None
        if arxiv_id:
            paper_url = f"https://arxiv.org/abs/{arxiv_id}"
        elif doi:
            paper_url = f"https://doi.org/{doi}"

        # 开放访问 PDF URL
        open_access = item.get("open_access") or {}
        pdf_url = open_access.get("oa_url")
        # 如果 oa_url 不是直接 PDF（不以 .pdf 结尾且不含 /pdf/），则不用作 pdf_url
        if pdf_url and not (pdf_url.endswith(".pdf") or "/pdf/" in pdf_url):
            pdf_url = None

        # 摘要重构（倒排索引 → 普通文本）
        abstract = self._reconstruct_abstract(
            item.get("abstract_inverted_index")
        )

        return PaperRecord(
            paper_id="",  # OpenAlex 不提供 S2 paper_id
            arxiv_id=arxiv_id,
            doi=doi,
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            venue=venue_normalized or venue_raw,
            venue_full=venue_info.get("full_name"),
            ccf_rank=venue_info.get("ccf_rank"),
            sci_tier=venue_info.get("sci_tier"),
            impact_factor=venue_info.get("impact_factor"),
            paper_url=paper_url,
            pdf_url=pdf_url,
            found_by=[PaperSource.OPENALEX],
            citation_count=item.get("cited_by_count"),
        )

    @staticmethod
    def _reconstruct_abstract(
        inverted_index: Optional[Dict[str, List[int]]]
    ) -> Optional[str]:
        """
        将 OpenAlex 的倒排索引格式摘要重构为普通文本。

        OpenAlex 的 abstract_inverted_index 格式：
            {"The": [0, 15], "model": [1], "achieves": [2], ...}
        需要翻转为位置→词的映射，再按位置排序，拼接为句子。

        Args:
            inverted_index: OpenAlex 返回的 abstract_inverted_index 字段

        Returns:
            重构后的摘要字符串，或 None（无摘要时）
        """
        if not inverted_index:
            return None

        # 翻转：{位置: 词}
        position_word: Dict[int, str] = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                position_word[pos] = word

        if not position_word:
            return None

        # 按位置排序后拼接
        sorted_words = [
            position_word[pos]
            for pos in sorted(position_word.keys())
        ]
        return " ".join(sorted_words)

    def _normalize_venue(self, venue_raw: str) -> str:
        """
        将 OpenAlex 来源名称映射到标准期刊/会议名称。
        按 key 长度降序匹配，优先用全称，再用词边界匹配 key 简称，
        防止 "PR" 误匹配含 "processing"/"pattern recognition" 的长字符串。
        """
        import re as _re

        if not venue_raw:
            return ""

        venue_lower = venue_raw.lower()
        sorted_venues = sorted(MONITORED_VENUES.items(), key=lambda x: len(x[0]), reverse=True)

        # 第一轮：全称精确子串匹配
        for key, info in sorted_venues:
            full_name = info.get("full_name", "").lower()
            if full_name and full_name in venue_lower:
                return key

        # 第二轮：key 词边界匹配
        for key, info in sorted_venues:
            pattern = r"\b" + _re.escape(key.lower()) + r"\b"
            if _re.search(pattern, venue_lower):
                return key

        return venue_raw
