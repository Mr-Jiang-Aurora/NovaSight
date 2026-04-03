"""
Agent1 搜索层 - CVF Open Access 爬取器
爬取 openaccess.thecvf.com 上的 CVPR/ICCV 论文，
使用 BeautifulSoup 解析 HTML，按领域关键词过滤。
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set

import aiohttp
from bs4 import BeautifulSoup

from config.knowledge_base import get_domain_info, MONITORED_VENUES
from config.settings import settings
from shared.models import PaperRecord, PaperSource, SearchResult
from shared.utils import extract_arxiv_id, clean_author_name
from .base_searcher import BaseSearcher

logger = logging.getLogger(__name__)

# CVF Open Access 基础 URL
CVF_BASE_URL = "https://openaccess.thecvf.com"

# 默认爬取年份范围（CVPR 每年，ICCV 奇数年）
DEFAULT_CVPR_YEARS = [2021, 2022, 2023, 2024, 2025]
DEFAULT_ICCV_YEARS = [2021, 2023, 2025]


class CVFSearcher(BaseSearcher):
    """
    CVF Open Access 爬取器。
    直接从 openaccess.thecvf.com 抓取论文列表，
    用领域关键词过滤出相关论文。
    不需要 API Key。
    """

    SOURCE_NAME = "CVF Open Access"
    MAX_RETRIES = 3

    def __init__(self) -> None:
        super().__init__()

    # ── 主入口 ────────────────────────────────────────────────────────

    async def search(self, domain: str) -> SearchResult:
        """
        爬取所有 search_in_cvf=True 的会议页面，
        按领域关键词过滤，返回相关论文。
        """
        start_time = time.monotonic()
        domain_info = get_domain_info(domain)
        all_papers: List[PaperRecord] = []
        errors: List[str] = []

        # 提取领域关键词（用于标题过滤，避免返回整届会议的数千篇）
        domain_keywords = self._build_domain_keywords(domain_info)

        # 遍历 CVF 支持的会议
        cvf_venues = {
            name: info
            for name, info in MONITORED_VENUES.items()
            if info.get("search_in_cvf", False) and info.get("cvf_name")
        }

        for venue_name, venue_info in cvf_venues.items():
            # 确定爬取年份范围
            if venue_name == "CVPR":
                years = DEFAULT_CVPR_YEARS
            elif venue_name == "ICCV":
                years = DEFAULT_ICCV_YEARS
            else:
                # 其他 CVF 会议按举办年份
                years = venue_info.get("held_years", DEFAULT_CVPR_YEARS)

            try:
                papers = await self.scrape_conference(
                    conf_name=venue_info["cvf_name"],
                    years=years,
                    domain_keywords=domain_keywords,
                    venue_name=venue_name,
                    venue_info=venue_info,
                )
                logger.info(
                    f"[CVF] {venue_name} ({years}) → {len(papers)} 篇相关论文"
                )
                all_papers.extend(papers)
            except Exception as e:
                err_msg = f"CVF 爬取失败 [{venue_name}]: {e}"
                logger.warning(f"[CVF] {err_msg}")
                errors.append(err_msg)

        elapsed = time.monotonic() - start_time
        return SearchResult(
            source=PaperSource.CVF_OPEN_ACCESS,
            domain=domain,
            query_used=f"CVF爬取：关键词={domain_keywords}",
            papers=all_papers,
            total_found=len(all_papers),
            search_time_seconds=elapsed,
            errors=errors,
        )

    # ── 核心爬取方法 ──────────────────────────────────────────────────

    async def scrape_conference(
        self,
        conf_name: str,
        years: List[int],
        domain_keywords: Set[str],
        venue_name: str,
        venue_info: Dict[str, Any],
    ) -> List[PaperRecord]:
        """
        爬取指定会议的多年论文列表。

        URL 格式（两种，需兼容处理）：
          2021年及以后：https://openaccess.thecvf.com/CVPR2021?day=all
          2020年及以前：https://openaccess.thecvf.com/CVPR2020.py

        Args:
            conf_name:       CVF 中的会议名，如 "CVPR"、"ICCV"
            years:           需要爬取的年份列表
            domain_keywords: 领域关键词集合（用于标题过滤）
            venue_name:      标准期刊/会议名，如 "CVPR"
            venue_info:      知识库中的会议信息

        Returns:
            过滤后的 PaperRecord 列表
        """
        all_papers: List[PaperRecord] = []

        for year in years:
            url = self._build_url(conf_name, year)
            logger.debug(f"[CVF] 爬取 {conf_name}{year}: {url}")

            try:
                html_content = await self._fetch_html(url)
                if not html_content:
                    logger.warning(f"[CVF] {conf_name}{year} 页面为空，跳过")
                    continue

                papers = self._parse_conference_page(
                    html_content=html_content,
                    conf_name=conf_name,
                    year=year,
                    domain_keywords=domain_keywords,
                    venue_name=venue_name,
                    venue_info=venue_info,
                )
                logger.debug(
                    f"[CVF] {conf_name}{year} 解析完成：{len(papers)} 篇相关论文"
                )
                all_papers.extend(papers)

            except Exception as e:
                logger.warning(f"[CVF] {conf_name}{year} 爬取/解析失败: {e}")

            # 会议页面之间加间隔
            await asyncio.sleep(settings.SEARCH_REQUEST_DELAY)

        return all_papers

    def _build_url(self, conf_name: str, year: int) -> str:
        """
        根据年份构建 CVF 页面 URL。
        2021年及以后用 ?day=all，2020年及以前用 .py 后缀。
        """
        if year >= 2021:
            return f"{CVF_BASE_URL}/{conf_name}{year}?day=all"
        else:
            return f"{CVF_BASE_URL}/{conf_name}{year}.py"

    async def _fetch_html(self, url: str) -> Optional[str]:
        """
        获取页面 HTML 内容（使用 aiohttp，含重试）。
        CVF 页面较大（数千篇论文），超时设置较长。
        """
        session = await self._get_session()
        timeout = aiohttp.ClientTimeout(total=60)  # CVF 页面较大，给 60 秒

        for attempt in range(1, self.MAX_RETRIES + 1):
            await self._rate_limit()
            try:
                async with session.get(url, timeout=timeout) as resp:
                    import time as _time
                    self._last_request_time = _time.monotonic()

                    if resp.status == 200:
                        return await resp.text(encoding="utf-8", errors="replace")
                    elif resp.status == 404:
                        logger.debug(f"[CVF] 404：{url}（该年份可能未举办）")
                        return None
                    else:
                        logger.warning(
                            f"[CVF] HTTP {resp.status}，第 {attempt} 次重试: {url}"
                        )
                        await asyncio.sleep(2.0 ** attempt)

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(
                    f"[CVF] 请求错误: {e}，第 {attempt}/{self.MAX_RETRIES} 次重试"
                )
                await asyncio.sleep(2.0 ** attempt)

        return None

    def _parse_conference_page(
        self,
        html_content: str,
        conf_name: str,
        year: int,
        domain_keywords: Set[str],
        venue_name: str,
        venue_info: Dict[str, Any],
    ) -> List[PaperRecord]:
        """
        解析 CVF Open Access 页面 HTML，提取论文信息。

        CVF 页面结构：
          <dt class="ptitle"><a href="...">论文标题</a></dt>
          <dd>
            <div class="authors">作者1, 作者2, ...</div>
            <div class="links">
              <a href="...pdf...">pdf</a>
              <a href="...arxiv...">arXiv</a>
            </div>
          </dd>
        """
        soup = BeautifulSoup(html_content, "lxml")
        papers: List[PaperRecord] = []

        # 找所有论文条目（dt.ptitle + 紧随的 dd 配对）
        dt_list = soup.find_all("dt", class_="ptitle")

        for dt in dt_list:
            # 提取标题
            title_tag = dt.find("a")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if not title:
                continue

            # 关键词过滤：只保留标题中含领域关键词的论文
            if not self._title_matches_domain(title, domain_keywords):
                continue

            # 紧随 dt 的第一个 dd 就是该论文的详情
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue

            # 作者
            authors_div = dd.find("div", class_="authors")
            authors: List[str] = []
            if authors_div:
                authors_text = authors_div.get_text(separator=",")
                authors = [
                    clean_author_name(a)
                    for a in authors_text.split(",")
                    if a.strip()
                ]

            # PDF 链接（CVF 页面中 text='pdf' 的 <a> 标签）
            pdf_url: Optional[str] = None
            arxiv_id: Optional[str] = None

            links_div = dd.find("div", class_="links")
            if links_div:
                for link in links_div.find_all("a"):
                    link_text = link.get_text(strip=True).lower()
                    href = link.get("href", "")

                    if link_text == "pdf" and href:
                        # 拼接完整 PDF URL（href 通常是相对路径）
                        if href.startswith("http"):
                            pdf_url = href
                        else:
                            pdf_url = f"{CVF_BASE_URL}{href}"

                    elif "arxiv" in link_text and href:
                        arxiv_id = extract_arxiv_id(href)

            # 论文 URL（优先 arXiv，其次 CVF 条目页）
            paper_url: Optional[str] = None
            if arxiv_id:
                paper_url = f"https://arxiv.org/abs/{arxiv_id}"
            elif title_tag.get("href"):
                href = title_tag["href"]
                paper_url = (
                    href if href.startswith("http")
                    else f"{CVF_BASE_URL}{href}"
                )

            papers.append(PaperRecord(
                paper_id="",
                arxiv_id=arxiv_id,
                title=title,
                authors=authors,
                year=year,
                venue=venue_name,
                venue_full=venue_info.get("full_name"),
                ccf_rank=venue_info.get("ccf_rank"),
                sci_tier=venue_info.get("sci_tier"),
                impact_factor=venue_info.get("impact_factor"),
                paper_url=paper_url,
                pdf_url=pdf_url,
                found_by=[PaperSource.CVF_OPEN_ACCESS],
            ))

        return papers

    # ── 辅助方法 ──────────────────────────────────────────────────────

    # 在 CV 领域中极为通用、单独出现不足以判断相关性的词
    _GENERIC_CV_WORDS: frozenset = frozenset({
        "object", "detection", "segmentation", "recognition", "tracking",
        "image", "images", "video", "visual", "vision", "scene", "feature",
        "network", "model", "learning", "deep", "neural", "attention",
        "transformer", "encoder", "decoder", "loss", "training", "benchmark",
        "dataset", "method", "approach", "framework", "module", "layer",
        "multi", "scale", "based", "via", "using", "with", "end", "toward",
        "towards", "new", "novel", "efficient", "fast", "real", "time",
        "joint", "unified", "universal", "general", "robust", "adaptive",
        "self", "unsupervised", "semi", "weakly", "zero", "few", "shot",
    })

    @staticmethod
    def _build_domain_keywords(domain_info: Dict[str, Any]) -> Set[str]:
        """
        从领域知识库的 search_queries 和数据集名称中提取过滤关键词集合。
        只保留领域特异性词汇（长度 >= 5，且不在通用 CV 词表中）。
        返回值分为：phrases（原始多词查询）和 specific_words（特异性单词）。
        实际存储格式：{"__phrase__:multi word query", "specific_word"}
        """
        keywords: Set[str] = set()
        stop_words = {"and", "or", "the", "for", "with", "on", "in", "of", "a"}
        generic_cv = CVFSearcher._GENERIC_CV_WORDS

        for query in domain_info.get("search_queries", []):
            query_lower = query.lower()
            # 保存完整短语（用于多词匹配）
            keywords.add(f"__phrase__:{query_lower}")
            # 提取特异性单词（长度>=5 且不是通用 CV 词）
            for word in query_lower.split():
                if len(word) >= 5 and word not in stop_words and word not in generic_cv:
                    keywords.add(word)

        # 数据集名称作为特异性关键词
        for dataset in domain_info.get("datasets", []):
            ds_lower = dataset.lower()
            if len(ds_lower) >= 3:
                keywords.add(ds_lower)

        return keywords

    @staticmethod
    def _title_matches_domain(title: str, domain_keywords: Set[str]) -> bool:
        """
        检查论文标题是否与领域相关（大小写不敏感）。

        匹配逻辑（OR 关系）：
          1. 标题中包含任一完整多词短语（高置信度）
          2. 标题中包含至少一个领域特异性单词（中置信度）

        Args:
            title:           论文标题
            domain_keywords: 关键词集合（含短语标记）

        Returns:
            True 表示匹配，应保留该论文
        """
        title_lower = title.lower()
        for kw in domain_keywords:
            if kw.startswith("__phrase__:"):
                phrase = kw[len("__phrase__:"):]
                if phrase in title_lower:
                    return True
            elif kw in title_lower:
                return True
        return False
