"""
Agent1 搜索层 - 抽象基类
所有搜索器（S2/OpenAlex/DBLP/CVF）均继承此类，
统一提供：HTTP 请求、速率限制、重试、日志、来源过滤等公共能力。
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import aiohttp

from config.knowledge_base import is_target_venue, get_domain_info
from config.settings import settings
from shared.models import PaperRecord, PaperSource, SearchResult

logger = logging.getLogger(__name__)


class BaseSearcher(ABC):
    """
    搜索器抽象基类。
    子类只需实现 search() 方法，其余公共能力由基类提供。
    """

    # 子类应覆盖此属性，用于日志标识
    SOURCE_NAME: str = "unknown"
    # 最大重试次数
    MAX_RETRIES: int = 3
    # 指数退避基数（秒）
    BACKOFF_BASE: float = 2.0

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        # 记录上次请求时间，用于速率限制
        self._last_request_time: float = 0.0

    # ── 抽象方法（子类必须实现）──────────────────────────────────────

    @abstractmethod
    async def search(self, domain: str) -> SearchResult:
        """
        执行该来源的完整搜索流程。

        Args:
            domain: 研究方向，如 "COD"、"SOD"

        Returns:
            SearchResult 对象，含论文列表和统计信息
        """
        ...

    # ── 公共 HTTP 请求（含重试 + 指数退避）─────────────────────────

    async def _make_request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送异步 GET 请求，自动重试（最多 MAX_RETRIES 次），指数退避。

        Args:
            url:     请求地址
            params:  URL 查询参数
            headers: 请求头
            timeout: 超时秒数，默认使用 settings.SEARCH_TIMEOUT

        Returns:
            响应 JSON（dict），或 None（所有重试均失败时）
        """
        if timeout is None:
            timeout = settings.SEARCH_TIMEOUT

        # 速率限制：等待到下次可请求时间
        await self._rate_limit()

        session = await self._get_session()
        request_timeout = aiohttp.ClientTimeout(total=timeout)

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=request_timeout,
                ) as resp:
                    self._last_request_time = time.monotonic()

                    if resp.status == 200:
                        return await resp.json(content_type=None)

                    elif resp.status == 429:
                        # 速率限制：等待更长时间
                        wait = self.BACKOFF_BASE ** attempt * 2
                        logger.warning(
                            f"[{self.SOURCE_NAME}] 429 速率限制，等待 {wait:.1f}s "
                            f"(第 {attempt}/{self.MAX_RETRIES} 次重试)"
                        )
                        await asyncio.sleep(wait)

                    elif resp.status in (500, 502, 503, 504):
                        # 服务端错误，重试
                        wait = self.BACKOFF_BASE ** attempt
                        logger.warning(
                            f"[{self.SOURCE_NAME}] HTTP {resp.status}，等待 {wait:.1f}s "
                            f"(第 {attempt}/{self.MAX_RETRIES} 次重试)"
                        )
                        await asyncio.sleep(wait)

                    else:
                        # 4xx 客户端错误，不重试
                        body = await resp.text()
                        logger.error(
                            f"[{self.SOURCE_NAME}] HTTP {resp.status}，URL={url}，"
                            f"响应: {body[:200]}"
                        )
                        return None

            except aiohttp.ClientError as e:
                wait = self.BACKOFF_BASE ** attempt
                logger.warning(
                    f"[{self.SOURCE_NAME}] 网络错误: {e}，等待 {wait:.1f}s "
                    f"(第 {attempt}/{self.MAX_RETRIES} 次重试)"
                )
                await asyncio.sleep(wait)

            except asyncio.TimeoutError:
                logger.warning(
                    f"[{self.SOURCE_NAME}] 请求超时（{timeout}s），"
                    f"第 {attempt}/{self.MAX_RETRIES} 次重试"
                )
                await asyncio.sleep(self.BACKOFF_BASE ** attempt)

        logger.error(f"[{self.SOURCE_NAME}] 请求失败（已重试 {self.MAX_RETRIES} 次）: {url}")
        return None

    # ── 速率限制 ──────────────────────────────────────────────────────

    async def _rate_limit(self) -> None:
        """
        基于上次请求时间，确保请求间隔不低于 settings.SEARCH_REQUEST_DELAY。
        使用 asyncio.sleep 不阻塞事件循环。
        """
        elapsed = time.monotonic() - self._last_request_time
        delay = settings.SEARCH_REQUEST_DELAY
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)

    # ── 来源过滤 ──────────────────────────────────────────────────────

    def _filter_by_venue(self, papers: List[PaperRecord]) -> List[PaperRecord]:
        """
        过滤论文列表，只保留发表在目标顶会/顶刊的论文。
        使用 knowledge_base.is_target_venue() 做模糊匹配。
        """
        filtered = [p for p in papers if is_target_venue(p.venue or "")]
        dropped = len(papers) - len(filtered)
        if dropped > 0:
            logger.debug(
                f"[{self.SOURCE_NAME}] 过滤掉 {dropped} 篇非目标期刊论文"
            )
        return filtered

    def _filter_by_year(
        self, papers: List[PaperRecord], min_year: int = 2019
    ) -> List[PaperRecord]:
        """过滤掉早于 min_year 的论文（搜索结果默认只要近年 SOTA）。"""
        return [p for p in papers if p.year is None or p.year >= min_year]

    # ── Session 管理 ──────────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp Session（懒初始化，复用连接池）。"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=10,           # 最大连接数
                limit_per_host=3,   # 每个 host 最大连接数
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                headers={"User-Agent": "SOD-COD-Research-Assistant/1.0 (academic research)"},
            )
        return self._session

    async def close(self) -> None:
        """关闭 HTTP Session，释放连接资源。"""
        if self._session and not self._session.closed:
            await self._session.close()

    # ── 上下文管理器支持 ──────────────────────────────────────────────

    async def __aenter__(self) -> "BaseSearcher":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
