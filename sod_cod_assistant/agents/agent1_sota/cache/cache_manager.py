"""
缓存管理器
负责读写 SOTA 排行榜缓存，管理 index.json。

缓存目录结构（默认在 cache/sota_cache/ 下）：
  COD.json        -- COD 领域全量论文缓存
  SOD.json        -- SOD 领域全量论文缓存
  index.json      -- 记录各 venue 最后处理的年份
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared.models import PaperRecord

logger = logging.getLogger(__name__)


class CacheManager:
    """缓存读写管理器"""

    INDEX_FILE = "index.json"

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / self.INDEX_FILE

    # ── 读取 ──────────────────────────────────────────────────────────

    def has_cache(self, domain: str) -> bool:
        """判断指定领域是否有缓存文件。"""
        return self._domain_cache_path(domain).exists()

    def load_cache(self, domain: str) -> Optional[list[PaperRecord]]:
        """读取指定领域的缓存论文列表，不存在时返回 None。"""
        cache_file = self._domain_cache_path(domain)
        if not cache_file.exists():
            return None
        try:
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
            papers = [PaperRecord(**p) for p in data.get("papers", [])]
            logger.info(
                f"缓存命中：{domain}，{len(papers)} 篇论文，"
                f"生成于 {data.get('generated_at', '未知')}"
            )
            return papers
        except Exception as e:
            logger.error(f"缓存读取失败：{e}")
            return None

    def load_index(self) -> dict:
        """读取 index.json，记录各 venue 最新处理年份。不存在时返回空字典。"""
        if not self.index_path.exists():
            return {}
        try:
            with open(self.index_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"index.json 读取失败：{e}")
            return {}

    # ── 写入 ──────────────────────────────────────────────────────────

    def save_cache(self, domain: str, papers: list[PaperRecord]) -> None:
        """将论文列表序列化写入缓存文件。"""
        cache_file = self._domain_cache_path(domain)
        data = {
            "domain": domain,
            "generated_at": datetime.now().isoformat(),
            "total": len(papers),
            "papers": [p.model_dump(mode="json") for p in papers],
        }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"缓存已保存：{cache_file}（{len(papers)} 篇）")

    def save_index(self, index: dict) -> None:
        """写入 index.json，自动追加 last_updated 时间戳。"""
        index["last_updated"] = datetime.now().isoformat()
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        logger.debug(f"index.json 已保存：{self.index_path}")

    def merge_new_papers(
        self,
        domain: str,
        existing: list[PaperRecord],
        new_papers: list[PaperRecord],
    ) -> list[PaperRecord]:
        """
        将新论文合并到现有缓存列表中（三级去重）。

        去重优先级：
          1. arxiv_id 精确匹配
          2. doi 精确匹配
          3. 标题相似度 > 0.90
        """
        from difflib import SequenceMatcher

        existing_arxiv  = {p.arxiv_id for p in existing if p.arxiv_id}
        existing_doi    = {p.doi for p in existing if p.doi}
        existing_titles = [p.title.lower() for p in existing if p.title]

        added = 0
        for np in new_papers:
            if np.arxiv_id and np.arxiv_id in existing_arxiv:
                continue
            if np.doi and np.doi in existing_doi:
                continue
            is_dup = any(
                SequenceMatcher(None, np.title.lower(), t).ratio() > 0.90
                for t in existing_titles
                if t
            )
            if is_dup:
                continue

            existing.append(np)
            added += 1

        logger.info(f"缓存合并：新增 {added} 篇，总计 {len(existing)} 篇")
        return existing

    # ── 内部工具 ──────────────────────────────────────────────────────

    def _domain_cache_path(self, domain: str) -> Path:
        safe_name = domain.replace(" ", "_").replace("/", "_")
        return self.cache_dir / f"{safe_name}.json"
