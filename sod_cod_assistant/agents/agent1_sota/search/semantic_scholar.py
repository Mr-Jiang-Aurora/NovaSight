"""
Agent1 搜索层 - Semantic Scholar 搜索器
实现两路搜索策略：
  1. 关键词搜索（Bulk Search API）
  2. 引用图谱扩展（Citations API，基于种子论文）
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

# Semantic Scholar API 基础 URL
S2_BASE_URL = "https://api.semanticscholar.org/graph/v1"

# 请求的论文字段（覆盖元数据 + 开放访问 PDF + 外部 ID）
S2_PAPER_FIELDS = (
    "title,year,venue,authors,citationCount,"
    "openAccessPdf,externalIds,abstract,influentialCitationCount"
)


class SemanticScholarSearcher(BaseSearcher):
    """
    Semantic Scholar 搜索器。
    优先使用 API Key 提高速率配额，无 Key 时降级到公共池。
    """

    SOURCE_NAME = "Semantic Scholar"
    # 有 API Key 时速率：1 RPS；无 Key 时公共池较慢
    MAX_RETRIES = 3

    def __init__(self) -> None:
        super().__init__()
        self._api_key = settings.SEMANTIC_SCHOLAR_API_KEY
        # 有 Key 时使用 1.0s 间隔，无 Key 时增大到 3.0s 降低被限频概率
        self._request_delay = 1.0 if self._api_key else 3.0

    def _build_headers(self) -> Dict[str, str]:
        """构建请求头，有 Key 时附加认证头。"""
        headers: Dict[str, str] = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    async def _rate_limit(self) -> None:
        """覆盖基类速率限制，根据是否有 Key 动态调整。"""
        import time as _time
        elapsed = _time.monotonic() - self._last_request_time
        if elapsed < self._request_delay:
            await asyncio.sleep(self._request_delay - elapsed)

    # ── 主入口 ────────────────────────────────────────────────────────

    async def search(self, domain: str) -> SearchResult:
        """
        执行 Semantic Scholar 全量搜索：
        1. 对每个 search_queries 条目执行关键词搜索
        2. 对种子论文执行引用图谱扩展
        3. 合并去重后返回
        """
        start_time = time.monotonic()
        domain_info = get_domain_info(domain)
        all_papers: List[PaperRecord] = []
        errors: List[str] = []

        # ── 第一步：关键词搜索 ────────────────────────────────────────
        for query in domain_info["search_queries"]:
            try:
                papers = await self.search_by_keywords(query)
                logger.info(
                    f"[S2] 关键词 '{query}' → {len(papers)} 篇（过滤后）"
                )
                all_papers.extend(papers)
            except Exception as e:
                err_msg = f"关键词搜索失败 '{query}': {e}"
                logger.warning(f"[S2] {err_msg}")
                errors.append(err_msg)

        # ── 第二步：引用图谱扩展 ──────────────────────────────────────
        seed_ids = domain_info.get("seed_paper_ids", [])
        if seed_ids:
            try:
                citation_papers = await self.expand_via_citations(seed_ids)
                logger.info(
                    f"[S2] 引用扩展（{len(seed_ids)} 篇种子论文）"
                    f"→ {len(citation_papers)} 篇新论文"
                )
                all_papers.extend(citation_papers)
            except Exception as e:
                err_msg = f"引用图谱扩展失败: {e}"
                logger.warning(f"[S2] {err_msg}")
                errors.append(err_msg)

        # ── 按 paper_id 简单去重（deduplicator 会做深度去重）──────────
        seen_ids: set[str] = set()
        unique_papers: List[PaperRecord] = []
        for p in all_papers:
            key = p.paper_id or p.arxiv_id or p.title
            if key and key not in seen_ids:
                seen_ids.add(key)
                unique_papers.append(p)

        elapsed = time.monotonic() - start_time
        logger.info(
            f"[S2] 搜索完成：去重后 {len(unique_papers)} 篇，"
            f"耗时 {elapsed:.1f}s"
        )

        return SearchResult(
            source=PaperSource.SEMANTIC_SCHOLAR,
            domain=domain,
            query_used="; ".join(domain_info["search_queries"]),
            papers=unique_papers,
            total_found=len(unique_papers),
            search_time_seconds=elapsed,
            errors=errors,
        )

    # ── 关键词批量搜索 ────────────────────────────────────────────────

    async def search_by_keywords(
        self,
        query: str,
        max_results: Optional[int] = None,
        min_year: int = 2019,
    ) -> List[PaperRecord]:
        """
        使用 Semantic Scholar Bulk Search 端点按关键词搜索论文。

        Args:
            query:      搜索关键词
            max_results: 最大返回数量，默认使用 settings.SEARCH_MAX_RESULTS_PER_SOURCE
            min_year:   最早发表年份过滤

        Returns:
            过滤后的 PaperRecord 列表
        """
        if max_results is None:
            max_results = settings.SEARCH_MAX_RESULTS_PER_SOURCE

        url = f"{S2_BASE_URL}/paper/search/bulk"
        params = {
            "query": query,
            "fields": S2_PAPER_FIELDS,
            "sort": "citationCount:desc",  # 按引用数降序，优先高影响力论文
            "limit": min(max_results, 100),  # Bulk Search 单次最多 100
        }

        data = await self._make_request(url, params=params, headers=self._build_headers())
        if not data:
            return []

        raw_papers = data.get("data", [])
        papers: List[PaperRecord] = []

        for item in raw_papers:
            paper = self._parse_paper_item(item)
            if paper is None:
                continue
            # 年份过滤
            if paper.year and paper.year < min_year:
                continue
            # 目标期刊过滤（S2 venue 字段质量较低，做模糊匹配）
            if not is_target_venue(paper.venue or ""):
                continue
            papers.append(paper)

        return papers

    # ── 引用图谱扩展 ──────────────────────────────────────────────────

    async def expand_via_citations(
        self,
        seed_paper_ids: List[str],
        min_year: int = 2019,
    ) -> List[PaperRecord]:
        """
        以种子论文为起点，获取其被引用列表（1 跳扩展），
        筛选出目标顶会/顶刊论文。

        Args:
            seed_paper_ids: 种子论文 ID 列表（支持 "ARXIV:xxxx" 格式）
            min_year:       最早发表年份过滤

        Returns:
            过滤后的引用论文列表
        """
        all_citing_papers: List[PaperRecord] = []

        for seed_id in seed_paper_ids:
            papers = await self._get_citations_for_paper(seed_id, min_year)
            all_citing_papers.extend(papers)
            # 种子论文之间加间隔，避免触发速率限制
            await self._rate_limit()

        return all_citing_papers

    async def _get_citations_for_paper(
        self, paper_id: str, min_year: int = 2019
    ) -> List[PaperRecord]:
        """
        获取单篇种子论文的引用列表。
        使用分页一次最多取 500 篇（实际限制每页 100 条，循环取）。
        """
        url = f"{S2_BASE_URL}/paper/{paper_id}/citations"
        params = {
            "fields": f"citingPaper.{S2_PAPER_FIELDS}",
            "limit": 100,
        }

        papers: List[PaperRecord] = []
        offset = 0
        max_pages = 5  # 最多取 5 页（500 条），避免无限循环

        for _ in range(max_pages):
            params["offset"] = offset
            data = await self._make_request(
                url, params=params, headers=self._build_headers()
            )
            if not data:
                break

            items = data.get("data", [])
            if not items:
                break

            for item in items:
                citing_paper_data = item.get("citingPaper", {})
                if not citing_paper_data:
                    continue
                paper = self._parse_paper_item(citing_paper_data)
                if paper is None:
                    continue
                if paper.year and paper.year < min_year:
                    continue
                if not is_target_venue(paper.venue or ""):
                    continue
                papers.append(paper)

            # 检查是否有下一页
            next_token = data.get("next")
            if not next_token:
                break
            offset += len(items)
            await self._rate_limit()

        logger.debug(
            f"[S2] 种子论文 {paper_id} 的引用扩展：找到 {len(papers)} 篇目标论文"
        )
        return papers

    # ── 数据解析 ──────────────────────────────────────────────────────

    def _parse_paper_item(self, item: Dict[str, Any]) -> Optional[PaperRecord]:
        """
        将 S2 API 返回的论文 JSON 解析为 PaperRecord。

        Args:
            item: S2 API 的单条论文数据

        Returns:
            PaperRecord，或 None（数据不足时）
        """
        title = (item.get("title") or "").strip()
        if not title:
            return None

        # 提取 arXiv ID 和 DOI（从 externalIds 字典）
        external_ids: Dict[str, str] = item.get("externalIds") or {}
        arxiv_id = extract_arxiv_id(external_ids.get("ArXiv", ""))
        doi = normalize_doi(external_ids.get("DOI", ""))
        corpus_id = str(external_ids.get("CorpusId", "")) or None

        # 作者列表
        authors_raw = item.get("authors") or []
        authors = [
            clean_author_name(a.get("name", ""))
            for a in authors_raw
            if a.get("name")
        ]

        # 开放访问 PDF URL
        oa_pdf = item.get("openAccessPdf") or {}
        pdf_url = oa_pdf.get("url") if oa_pdf else None

        # arXiv 论文 URL
        paper_url: Optional[str] = None
        if arxiv_id:
            paper_url = f"https://arxiv.org/abs/{arxiv_id}"
        elif doi:
            paper_url = f"https://doi.org/{doi}"

        # 发表来源（venue 字段质量较低，需要模糊匹配）
        venue_raw = (item.get("venue") or "").strip()
        # 尝试从 venue 字符串中识别标准期刊/会议名
        venue_normalized = self._normalize_venue(venue_raw)

        # 从 knowledge_base 补充 CCF 等级和 SCI 分区
        venue_info = self._get_venue_metadata(venue_normalized)

        return PaperRecord(
            paper_id=item.get("paperId", ""),
            arxiv_id=arxiv_id,
            doi=doi,
            s2_corpus_id=corpus_id,
            title=title,
            authors=authors,
            year=item.get("year"),
            abstract=item.get("abstract"),
            venue=venue_normalized or venue_raw,
            venue_full=venue_info.get("full_name"),
            ccf_rank=venue_info.get("ccf_rank"),
            sci_tier=venue_info.get("sci_tier"),
            impact_factor=venue_info.get("impact_factor"),
            paper_url=paper_url,
            pdf_url=pdf_url,
            found_by=[PaperSource.SEMANTIC_SCHOLAR],
            citation_count=item.get("citationCount"),
        )

    def _normalize_venue(self, venue_raw: str) -> str:
        """
        将 S2 返回的原始 venue 字符串映射到标准期刊/会议名称。
        S2 的 venue 字段质量参差不齐，如：
          "IEEE Transactions on Pattern Analysis..." → "IEEE TPAMI"
          "2024 IEEE/CVF Conference..."             → "CVPR"
          "ArXiv"                                   → ""（不是目标期刊）

        匹配策略（按优先级）：
          1. 全称精确包含（最高优先，用于区分 CVPR vs PR 等）
          2. key 词边界匹配（防止 "PR" 误匹配 "processing" 中的 "pr"）
          3. dblp_key 后缀大写匹配
        排序：按 key 长度降序，避免短 key 先匹配到长全称的片段。
        """
        import re as _re

        if not venue_raw:
            return ""

        venue_lower = venue_raw.lower()

        # 按 key 长度降序排序，确保长且具体的名称优先匹配
        sorted_venues = sorted(MONITORED_VENUES.items(), key=lambda x: len(x[0]), reverse=True)

        # 第一轮：用全称做精确子串匹配（全称更长，不易产生误匹配）
        for key, info in sorted_venues:
            full_name = info.get("full_name", "").lower()
            if full_name and full_name in venue_lower:
                return key

        # 第二轮：用 key 做词边界匹配（防止 "PR" 匹配到 "pattern recognition" 内部）
        for key, info in sorted_venues:
            pattern = r"\b" + _re.escape(key.lower()) + r"\b"
            if _re.search(pattern, venue_lower):
                return key

        # 第三轮：用 dblp_key 的会议名大写匹配（如 "PAMI" 在 venue 中）
        for key, info in sorted_venues:
            dblp_key_str = info.get("dblp_key", "")
            if dblp_key_str:
                conf_name = dblp_key_str.split("/")[-1].upper()
                pattern = r"\b" + _re.escape(conf_name) + r"\b"
                if _re.search(pattern, venue_raw.upper()):
                    return key

        # 未能匹配到标准名称，返回原始值（供 is_target_venue 做二次模糊匹配）
        return venue_raw

    def _get_venue_metadata(self, venue_name: str) -> Dict[str, Any]:
        """从知识库获取期刊/会议的 CCF 等级和 SCI 分区。"""
        return MONITORED_VENUES.get(venue_name, {})
