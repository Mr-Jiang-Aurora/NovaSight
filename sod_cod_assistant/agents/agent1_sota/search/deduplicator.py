"""
Agent1 搜索层 - 论文去重合并器
实现四源搜索结果的去重与信息合并。
去重优先级：arXiv ID > DOI > 标题精确匹配 > 标题相似度 > 0.92
"""

from __future__ import annotations

import difflib
import logging
from typing import Dict, List, Optional, Tuple

from shared.models import PaperRecord, PaperSource
from shared.utils import normalize_title, title_similarity

logger = logging.getLogger(__name__)

# 标题相似度阈值（>= 此值视为重复）
TITLE_SIMILARITY_THRESHOLD = 0.92


class PaperDeduplicator:
    """
    四源论文结果去重器。
    合并来自 Semantic Scholar、OpenAlex、DBLP、CVF 的重复记录，
    保留信息最完整的版本，并在 found_by 中记录所有来源。
    """

    def deduplicate(self, papers: List[PaperRecord]) -> List[PaperRecord]:
        """
        对论文列表进行去重合并。

        去重逻辑（优先级从高到低）：
          1. arXiv ID 相同 → 重复
          2. DOI 相同 → 重复
          3. 标题 normalized 后完全相同 → 重复
          4. 标题相似度 > 0.92 → 重复

        合并策略：多条重复记录合并时，每个字段取「非空值中最先找到的」，
        并将所有来源记录在 found_by 列表中（去重）。

        Args:
            papers: 来自所有搜索源的论文列表（允许有重复）

        Returns:
            去重合并后的论文列表
        """
        if not papers:
            return []

        original_count = len(papers)

        # 用并查集（Union-Find）思路处理重复关系
        # 每个 paper 分配索引，合并时指向主记录
        parent: List[int] = list(range(len(papers)))

        def find(x: int) -> int:
            """找到 x 的根节点（路径压缩）。"""
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            """将 x 和 y 合并（保留较小索引作为主记录）。"""
            rx, ry = find(x), find(y)
            if rx != ry:
                # 保留索引较小的作为主记录（信息越完整越靠前排列）
                parent[max(rx, ry)] = min(rx, ry)

        # ── 第1轮：按 arXiv ID 去重 ─────────────────────────────────
        arxiv_index: Dict[str, int] = {}
        for i, paper in enumerate(papers):
            if not paper.arxiv_id:
                continue
            aid = paper.arxiv_id.lower()
            if aid in arxiv_index:
                union(i, arxiv_index[aid])
            else:
                arxiv_index[aid] = i

        # ── 第2轮：按 DOI 去重 ──────────────────────────────────────
        doi_index: Dict[str, int] = {}
        for i, paper in enumerate(papers):
            if not paper.doi:
                continue
            doi_key = paper.doi.lower()
            if doi_key in doi_index:
                union(i, doi_index[doi_key])
            else:
                doi_index[doi_key] = i

        # ── 第3轮：按标题精确匹配去重 ──────────────────────────────
        title_index: Dict[str, int] = {}
        for i, paper in enumerate(papers):
            if not paper.title:
                continue
            norm = normalize_title(paper.title)
            if not norm:
                continue
            if norm in title_index:
                union(i, title_index[norm])
            else:
                title_index[norm] = i

        # ── 第4轮：按标题相似度去重（前缀分桶降低比较量）──────────────
        # 策略：先用 normalized title 的前 8 个字符做桶分组，
        # 只在同桶或相邻桶内比较，大幅减少无效比较（通常 95%+ 节省）。
        roots_now = list({find(i) for i in range(len(papers))})

        # 为每个根节点建立标题前缀桶
        prefix_buckets: Dict[str, List[int]] = {}
        for r in roots_now:
            title_norm = normalize_title(papers[r].title or "")
            prefix = title_norm[:8] if len(title_norm) >= 8 else title_norm
            prefix_buckets.setdefault(prefix, []).append(r)

        # 只在同桶内比较（同前缀 → 大概率相似标题）
        for bucket_roots in prefix_buckets.values():
            if len(bucket_roots) < 2:
                continue
            for idx_a in range(len(bucket_roots)):
                for idx_b in range(idx_a + 1, len(bucket_roots)):
                    ra, rb = bucket_roots[idx_a], bucket_roots[idx_b]
                    if find(ra) == find(rb):
                        continue  # 已合并
                    sim = title_similarity(papers[ra].title, papers[rb].title)
                    if sim >= TITLE_SIMILARITY_THRESHOLD:
                        logger.debug(
                            f"[去重] 相似度 {sim:.3f}，合并：\n"
                            f"  A: {papers[ra].title}\n"
                            f"  B: {papers[rb].title}"
                        )
                        union(ra, rb)

        # ── 按合并关系分组 ────────────────────────────────────────────
        groups: Dict[int, List[int]] = {}
        for i in range(len(papers)):
            root = find(i)
            groups.setdefault(root, []).append(i)

        # ── 对每组进行合并，生成最终结果 ─────────────────────────────
        merged_papers: List[PaperRecord] = []
        for root, indices in groups.items():
            if len(indices) == 1:
                merged_papers.append(papers[indices[0]])
            else:
                merged = self._merge_group([papers[i] for i in indices])
                merged_papers.append(merged)

        dedup_count = original_count - len(merged_papers)
        logger.info(
            f"[去重] 输入 {original_count} 篇 → 去重后 {len(merged_papers)} 篇"
            f"（合并了 {dedup_count} 条重复记录）"
        )

        return merged_papers

    def _merge_group(self, papers: List[PaperRecord]) -> PaperRecord:
        """
        合并一组重复的论文记录，每个字段取「非空值中最先找到的」。
        所有来源都记录在 found_by 中（去重）。

        选取策略：
          - 优先保留字段更完整（非 None 字段更多）的记录作为主记录
          - 再逐字段补充其他记录中的非空值

        Args:
            papers: 确认为同一篇论文的多条记录

        Returns:
            合并后的单条 PaperRecord
        """
        # 按字段完整度降序排列（字段更多的排前面）
        sorted_papers = sorted(
            papers,
            key=lambda p: self._completeness_score(p),
            reverse=True,
        )

        # 以最完整的记录作为基础
        base = sorted_papers[0].model_copy(deep=True)

        # 逐字段补充：如果 base 中某字段为空，从其他记录中取第一个非空值
        for other in sorted_papers[1:]:
            # 标识符：优先保留 S2 paper_id
            if not base.paper_id and other.paper_id:
                base.paper_id = other.paper_id
            if not base.arxiv_id and other.arxiv_id:
                base.arxiv_id = other.arxiv_id
            if not base.doi and other.doi:
                base.doi = other.doi
            if not base.s2_corpus_id and other.s2_corpus_id:
                base.s2_corpus_id = other.s2_corpus_id

            # 元数据
            if not base.abstract and other.abstract:
                base.abstract = other.abstract
            if not base.authors and other.authors:
                base.authors = other.authors
            if base.year is None and other.year is not None:
                base.year = other.year
            if base.citation_count is None and other.citation_count is not None:
                base.citation_count = other.citation_count

            # 发表信息
            if not base.venue and other.venue:
                base.venue = other.venue
            if not base.venue_full and other.venue_full:
                base.venue_full = other.venue_full
            if not base.ccf_rank and other.ccf_rank:
                base.ccf_rank = other.ccf_rank
            if not base.sci_tier and other.sci_tier:
                base.sci_tier = other.sci_tier
            if base.impact_factor is None and other.impact_factor is not None:
                base.impact_factor = other.impact_factor

            # 链接
            if not base.paper_url and other.paper_url:
                base.paper_url = other.paper_url
            if not base.pdf_url and other.pdf_url:
                base.pdf_url = other.pdf_url
            if not base.code_url and other.code_url:
                base.code_url = other.code_url

        # 合并所有来源（去重，保持顺序）
        all_sources: List[PaperSource] = []
        seen_sources: set = set()
        for p in papers:
            for src in p.found_by:
                if src not in seen_sources:
                    all_sources.append(src)
                    seen_sources.add(src)
        base.found_by = all_sources

        return base

    @staticmethod
    def _completeness_score(paper: PaperRecord) -> int:
        """
        计算论文记录的字段完整度分数（非 None 且非空字符串的字段数）。
        分数越高表示记录越完整，合并时优先保留。
        """
        score = 0
        for field_name in [
            "paper_id", "arxiv_id", "doi", "title", "abstract",
            "venue", "venue_full", "ccf_rank", "paper_url", "pdf_url",
        ]:
            val = getattr(paper, field_name, None)
            if val:
                score += 1
        if paper.authors:
            score += 1
        if paper.year is not None:
            score += 1
        if paper.citation_count is not None:
            score += 1
        return score
