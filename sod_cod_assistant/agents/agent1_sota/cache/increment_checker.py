"""
增量更新检测器
通过 DBLP API 查询各监控期刊/会议的最新年份，
与 index.json 中记录的上次处理年份对比，
判断哪些 venue 有新论文需要更新。
"""

import logging
import time
from datetime import datetime

import requests

from config.knowledge_base import MONITORED_VENUES

logger = logging.getLogger(__name__)

DBLP_VENUE_URL = "https://dblp.org/search/publ/api"


class IncrementChecker:
    """增量更新检测器"""

    def __init__(self, cache_manager):
        self.cache_manager = cache_manager

    def check_for_updates(self, domain: str) -> dict[str, bool]:
        """
        检查各监控 venue 是否有新论文。

        Returns:
            {venue_name: has_new_papers}
            例如 {"CVPR": True, "IEEE TPAMI": False, ...}
        """
        index = self.cache_manager.load_index()
        domain_index = index.get(domain, {})

        results = {}
        current_year = datetime.now().year

        for venue_name, venue_info in MONITORED_VENUES.items():
            try:
                has_new = self._check_venue(
                    venue_name, venue_info, domain_index, current_year
                )
                results[venue_name] = has_new
                time.sleep(1)  # DBLP 礼貌延迟

            except Exception as e:
                logger.warning(f"检查 {venue_name} 失败：{e}，默认视为有更新")
                results[venue_name] = True

        new_count = sum(1 for v in results.values() if v)
        logger.info(
            f"增量检测完成：{new_count}/{len(results)} 个 venue 有新内容"
        )
        return results

    def _check_venue(
        self,
        venue_name: str,
        venue_info: dict,
        domain_index: dict,
        current_year: int,
    ) -> bool:
        """检查单个 venue 是否有新论文。"""
        venue_type      = venue_info.get("type", "conference")
        dblp_key        = venue_info.get("dblp_key", "")
        last_processed  = domain_index.get(venue_name, {})

        if venue_type == "journal":
            return self._check_journal(venue_name, dblp_key, last_processed)
        else:
            return self._check_conference(
                venue_name, venue_info, last_processed, current_year
            )

    def _check_journal(
        self, venue_name: str, dblp_key: str, last_processed: dict
    ) -> bool:
        """
        通过 DBLP API 查询期刊最新一篇论文的年份，
        与 index.json 记录的上次处理年份对比。
        """
        if not dblp_key:
            last_year = last_processed.get("last_year", 0)
            return datetime.now().year > last_year

        try:
            resp = requests.get(
                DBLP_VENUE_URL,
                params={
                    "q": f"stream:streams/{dblp_key}:",
                    "format": "json",
                    "h": 1,
                    "c": 0,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            hits = data.get("result", {}).get("hits", {}).get("hit", [])
            if not hits:
                return False

            latest_year = int(hits[0].get("info", {}).get("year", 0))
            last_year   = last_processed.get("last_year", 0)

            has_new = latest_year > last_year
            if has_new:
                logger.info(
                    f"{venue_name}：有新内容（最新年份 {latest_year}，"
                    f"上次处理 {last_year}）"
                )
            return has_new

        except Exception as e:
            logger.debug(f"_check_journal 失败 {venue_name}: {e}")
            return True

    def _check_conference(
        self,
        venue_name: str,
        venue_info: dict,
        last_processed: dict,
        current_year: int,
    ) -> bool:
        """
        检查会议是否有新一届论文。
        隔年举办的会议（如 ICCV/ECCV）先判断今年是否举办。
        """
        held_every_year = venue_info.get("held_every_year", True)
        held_years      = venue_info.get("held_years", [])

        if not held_every_year and held_years:
            if current_year not in held_years:
                logger.debug(f"{venue_name}：{current_year} 年不举办，跳过")
                return False

        last_year = last_processed.get("last_year", 0)
        has_new   = current_year > last_year

        if has_new:
            logger.info(
                f"{venue_name}：有新内容（当前年份 {current_year}，"
                f"上次处理 {last_year}）"
            )
        return has_new

    def update_index(self, domain: str, venues_updated: list[str]) -> None:
        """
        将已处理的 venue 更新到 index.json，
        记录本次处理年份供下次增量检测使用。
        """
        index = self.cache_manager.load_index()
        if domain not in index:
            index[domain] = {}

        current_year = datetime.now().year
        for venue_name in venues_updated:
            index[domain][venue_name] = {
                "last_year": current_year,
                "last_updated": datetime.now().isoformat(),
            }

        self.cache_manager.save_index(index)
        logger.info(f"index.json 已更新：{len(venues_updated)} 个 venue")
