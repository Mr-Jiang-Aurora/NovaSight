"""
PDF 获取层 - 优先级5：CORE API 终极兜底
覆盖 4.31 亿篇全文记录，是最大的开放获取数据库。
CORE API Key 为可选，未配置时自动跳过整个 CORE 路。
申请地址（免费）：https://core.ac.uk/services/api#form
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from shared.models import PaperRecord

logger = logging.getLogger(__name__)


class COREFetcher:
    """CORE API 兜底获取器（优先级 5）"""

    BASE_URL = "https://api.core.ac.uk/v3"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key
        self.enabled = bool(api_key)
        if not self.enabled:
            logger.info(
                "[CORE] API Key 未配置，CORE 兜底将被跳过。"
                "（申请地址：https://core.ac.uk/services/api#form）"
            )

    async def get_pdf_url(self, paper: "PaperRecord") -> Optional[str]:
        """
        尝试通过 DOI（精确）或标题（模糊）从 CORE 获取 PDF 链接。
        未启用时直接返回 None。
        """
        if not self.enabled:
            return None

        # 优先用 DOI 精确查询
        if paper.doi:
            result = await self._query_by_doi(paper.doi)
            if result:
                return result

        # 其次用标题模糊查询
        if paper.title:
            result = await self._query_by_title(paper.title)
            if result:
                return result

        return None

    async def _query_by_doi(self, doi: str) -> Optional[str]:
        """通过 DOI 精确查询 CORE"""
        clean_doi = doi.strip().lstrip("https://doi.org/")
        return await self._execute_query({"q": f'doi:"{clean_doi}"', "limit": 1})

    async def _query_by_title(self, title: str) -> Optional[str]:
        """通过标题前 60 字符模糊查询 CORE"""
        short = title[:60].replace('"', ' ')
        return await self._execute_query({"q": f'title:"{short}"', "limit": 1})

    async def _execute_query(self, params: dict) -> Optional[str]:
        """执行 CORE API 查询，返回 downloadUrl 或 fullTextLink"""
        params["apiKey"] = self.api_key
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/search/works",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=20),
                    headers={"User-Agent": "SOD-COD-Research-Assistant/1.0"},
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    results = data.get("results", [])
                    if not results:
                        return None
                    first = results[0]
                    return first.get("downloadUrl") or first.get("fullTextLink")
        except Exception as e:
            logger.debug(f"[CORE] 查询异常：{e}")
            return None
