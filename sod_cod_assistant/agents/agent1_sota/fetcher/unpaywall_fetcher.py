"""
PDF 获取层 - 优先级4：Unpaywall API
专门处理有 DOI 的期刊论文（IEEE TPAMI/TIP/IJCV/PR/TCSVT 等）
成功率约 50-70%，API 完全免费，无需注册，只需提供邮箱。

注意：email 参数不是订阅邮箱，只是 API 的身份识别参数，
Unpaywall 不会向该邮箱发送任何邮件。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from shared.models import PaperRecord

logger = logging.getLogger(__name__)


class UnpywallFetcher:
    """
    Unpaywall API 获取器（优先级 4）
    通过 DOI 查询 Unpaywall，提取最优开放获取 PDF 链接。
    """

    BASE_URL = "https://api.unpaywall.org/v2"

    def __init__(self, email: str) -> None:
        if not email or "@" not in email:
            raise ValueError(
                "Unpaywall 需要有效的邮箱地址作为 email 参数。\n"
                "请在 .env 文件中设置 UNPAYWALL_EMAIL=your@email.com"
            )
        self.email = email
        # DOI → PDF URL 的小型内存缓存（避免重复请求）
        self._cache: dict[str, Optional[str]] = {}

    async def get_pdf_url(self, paper: "PaperRecord") -> Optional[str]:
        """
        通过 DOI 查询 Unpaywall，提取最优开放获取 PDF 链接。
        若 DOI 不存在则直接返回 None。
        """
        if not paper.doi:
            return None

        # 规范化 DOI（去除 https://doi.org/ 前缀）
        doi = (
            paper.doi.strip()
            .lstrip("https://doi.org/")
            .lstrip("http://dx.doi.org/")
        )

        if doi in self._cache:
            return self._cache[doi]

        url = f"{self.BASE_URL}/{doi}"
        params = {"email": self.email}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers={"User-Agent": "SOD-COD-Research-Assistant/1.0"},
                ) as resp:

                    if resp.status == 404:
                        self._cache[doi] = None
                        return None

                    if resp.status != 200:
                        logger.debug(f"[Unpaywall] HTTP {resp.status} for DOI: {doi}")
                        return None

                    data = await resp.json()
                    pdf_url = self._extract_best_pdf(data)
                    self._cache[doi] = pdf_url
                    return pdf_url

        except asyncio.TimeoutError:
            logger.debug(f"[Unpaywall] 超时：{doi}")
            return None
        except Exception as e:
            logger.debug(f"[Unpaywall] 异常：{doi} → {e}")
            return None

    def _extract_best_pdf(self, data: dict) -> Optional[str]:
        """
        从 Unpaywall 响应中提取最优 PDF 链接。

        字段说明：
          is_oa: 是否有开放获取版本
          best_oa_location.url_for_pdf: 直接 PDF 链接（最优）
          best_oa_location.url: 论文页面（备用）
          best_oa_location.host_type: publisher/repository/preprint
        """
        if not data.get("is_oa"):
            return None

        best = data.get("best_oa_location")
        if not best:
            return None

        # 优先直接 PDF 链接
        pdf_url = best.get("url_for_pdf")
        if pdf_url:
            return pdf_url

        # 次选：论文页面链接（后续可手动确认）
        return best.get("url")

    async def batch_get_pdf_urls(
        self,
        papers: list["PaperRecord"],
        delay: float = 0.1,
    ) -> dict[str, Optional[str]]:
        """
        串行批量查询（避免超速，Unpaywall 10 万次/天限额足够）。
        只处理有 DOI 且尚未获取 PDF 的论文。
        """
        results: dict[str, Optional[str]] = {}
        doi_papers = [p for p in papers if p.doi and not p.pdf_url]
        logger.info(f"[Unpaywall] 需查询 {len(doi_papers)} 篇有 DOI 的论文")

        for paper in doi_papers:
            url = await self.get_pdf_url(paper)
            results[paper.paper_id] = url
            await asyncio.sleep(delay)  # 100ms 间隔

        return results
