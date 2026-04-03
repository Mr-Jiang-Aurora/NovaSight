"""
PDF 获取层 - 优先级2：顶会开放库直链
覆盖：CVF（CVPR/ICCV/WACV）、NeurIPS
对这些会议论文，PDF 获取成功率接近 100%
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from shared.models import PaperRecord

logger = logging.getLogger(__name__)


class ConferenceFetcher:
    """
    顶会开放库直链获取器（优先级 2）
    根据 venue 字段选择对应的会议开放库进行 PDF 链接构造/验证。
    """

    CVF_BASE     = "https://openaccess.thecvf.com"
    NEURIPS_BASE = "https://proceedings.neurips.cc"

    async def get_pdf_url(self, paper: "PaperRecord") -> Optional[str]:
        """根据 venue 分发到对应的会议获取方法"""
        venue = (paper.venue or "").upper()

        # CVF 系列（CVPR / ICCV / WACV）
        if any(v in venue for v in ["CVPR", "ICCV", "WACV"]):
            # Phase 1 搜索时已填充了 CVF pdf_url，优先验证已有 URL
            if paper.pdf_url and "thecvf.com" in paper.pdf_url:
                if await self._check_accessible(paper.pdf_url):
                    return paper.pdf_url
            return await self._try_cvf_pdf(paper)

        # NeurIPS
        if "NEURIPS" in venue or "NIPS" in venue:
            return await self._try_neurips_pdf(paper)

        return None

    async def _try_cvf_pdf(self, paper: "PaperRecord") -> Optional[str]:
        """
        从 CVF 详情页 URL 推导 PDF 链接。

        新格式（2021+）：
          详情页：/content/CVPR2024/html/Author_Title_CVPR_2024_paper.html
          PDF：   /content/CVPR2024/papers/Author_Title_CVPR_2024_paper.pdf

        旧格式（2020-）：
          详情页：/content_cvpr_2020/html/Author_Title_CVPR_2020_paper.html
          PDF：   /content_cvpr_2020/papers/Author_Title_CVPR_2020_paper.pdf
        """
        if not paper.paper_url:
            return None

        detail_url = paper.paper_url
        if "/html/" in detail_url and detail_url.endswith(".html"):
            pdf_path = (
                detail_url
                .replace("/html/", "/papers/")
                .replace(".html", ".pdf")
            )
            full_url = (
                pdf_path if pdf_path.startswith("http")
                else self.CVF_BASE + pdf_path
            )
            if await self._check_accessible(full_url):
                return full_url

        return None

    async def _try_neurips_pdf(self, paper: "PaperRecord") -> Optional[str]:
        """
        构造 NeurIPS PDF 链接。
          详情页：.../hash/xxxxx-Abstract-Conference.html
          PDF：   .../file/xxxxx-Paper-Conference.pdf
        """
        if not paper.paper_url or "neurips.cc" not in paper.paper_url:
            return None

        url = paper.paper_url
        if "-Abstract-" in url:
            pdf_url = (
                url.replace("-Abstract-", "-Paper-")
                   .replace(".html", ".pdf")
            )
            if await self._check_accessible(pdf_url):
                return pdf_url

        return None

    async def _check_accessible(self, url: str, timeout: int = 10) -> bool:
        """HEAD 请求验证 URL 可达性"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True,
                    headers={"User-Agent": "SOD-COD-Research-Assistant/1.0"},
                ) as resp:
                    return resp.status in (200, 302)
        except Exception as e:
            logger.debug(f"[Conference] HEAD 请求失败 {url}: {e}")
            return False
