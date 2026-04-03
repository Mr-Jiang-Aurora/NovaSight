"""
PDF 获取层 - 优先级1：arXiv 直链构造器
无需任何 API Key，成功率约 70-80%（对有 arXiv 预印本的论文）
"""

from __future__ import annotations

import re
import asyncio
import logging
from typing import Optional, TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from shared.models import PaperRecord

logger = logging.getLogger(__name__)


class ArXivFetcher:
    """
    arXiv 直链构造器（优先级 1）
    直接构造 https://arxiv.org/pdf/{arxiv_id} 并验证可达性。
    """

    BASE_PDF_URL = "https://arxiv.org/pdf"

    # 匹配新格式（2301.12345）和旧格式（cs/0612071）
    ARXIV_ID_PATTERN = re.compile(
        r'(?:arxiv[.:/]?\s*)?((?:\d{4}\.\d{4,5}(?:v\d+)?)|(?:[a-z\-]+/\d{7}))',
        re.IGNORECASE,
    )

    async def get_pdf_url(self, paper: "PaperRecord") -> Optional[str]:
        """
        提取 arXiv ID，构造 PDF 直链，通过 HEAD 请求验证可达性。
        返回可用的 PDF URL，或 None（无 arXiv ID 或链接不可达）。
        """
        arxiv_id = self._extract_arxiv_id(paper)
        if not arxiv_id:
            return None

        # 去除版本号（如 v1、v2），使用最新版
        arxiv_id_clean = re.sub(r'v\d+$', '', arxiv_id)
        pdf_url = f"{self.BASE_PDF_URL}/{arxiv_id_clean}"

        if await self._check_accessible(pdf_url):
            # 回写 arxiv_id 字段（方便后续使用）
            if not paper.arxiv_id:
                paper.arxiv_id = arxiv_id_clean
            return pdf_url

        return None

    def _extract_arxiv_id(self, paper: "PaperRecord") -> Optional[str]:
        """
        从论文记录的各字段中提取 arXiv ID。
        优先级：arxiv_id 字段 > paper_url > pdf_url > external_ids
        """
        # 1. 直接字段
        if paper.arxiv_id:
            return paper.arxiv_id.strip()

        # 2. 从 URL 字段解析
        for url_field in [paper.paper_url, paper.pdf_url]:
            if url_field and "arxiv.org" in url_field.lower():
                m = self.ARXIV_ID_PATTERN.search(url_field)
                if m:
                    return m.group(1)

        # 3. 从 external_ids 字段（S2 API 返回）
        if hasattr(paper, "external_ids") and paper.external_ids:
            aid = paper.external_ids.get("ArXiv")
            if aid:
                return aid

        return None

    async def _check_accessible(self, url: str, timeout: int = 10) -> bool:
        """HEAD 请求检查 URL 可达性（跟随重定向，arXiv 存在 301 跳转）"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True,
                    headers={
                        "User-Agent": "SOD-COD-Research-Assistant/1.0 (Nankai University)"
                    },
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.debug(f"[ArXiv] HEAD 请求失败 {url}: {e}")
            return False

    async def batch_get_pdf_urls(
        self,
        papers: list["PaperRecord"],
        max_concurrent: int = 5,
    ) -> dict[str, Optional[str]]:
        """并发批量获取（最多 5 个并发，礼貌控制）"""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _get_one(paper: "PaperRecord"):
            async with semaphore:
                url = await self.get_pdf_url(paper)
                await asyncio.sleep(0.3)  # 礼貌延迟 300ms
                return paper.paper_id, url

        tasks = [_get_one(p) for p in papers if not p.pdf_url]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            pid: url
            for pid, url in results
            if not isinstance(url, Exception) and url is not None
        }
