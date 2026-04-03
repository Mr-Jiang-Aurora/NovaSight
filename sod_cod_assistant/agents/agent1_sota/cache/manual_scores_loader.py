"""
手动分数导入器
从 cache/manual_scores.json 加载人工录入的论文分数，
合并到现有的 PaperRecord 列表中。

合并规则：
  1. arXiv ID 精确匹配 → 找到则覆盖分数
  2. 标题相似度匹配（> 0.85）→ 找到则覆盖分数
  3. 两者都找不到 → 新建 PaperRecord 并加入列表
"""

import json
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from shared.models import (
    PaperRecord, MetricScores, ExtractionConfidence,
)

logger = logging.getLogger(__name__)


class ManualScoresLoader:
    """手动分数导入器"""

    TITLE_SIMILARITY_THRESHOLD = 0.85

    def __init__(self, manual_scores_path: str = "cache/manual_scores.json"):
        self.path = Path(manual_scores_path)

    def load_and_merge(
        self,
        papers: list[PaperRecord],
        domain: str,
    ) -> tuple[list[PaperRecord], dict]:
        """
        加载手动分数文件，与现有论文列表合并。

        Args:
            papers: 现有论文列表
            domain: 研究领域（用于过滤数据集）

        Returns:
            (merged_papers, stats)
              stats = {"loaded": int, "matched": int, "new_added": int}
        """
        if not self.path.exists():
            logger.info(f"手动分数文件不存在：{self.path}，跳过")
            return papers, {"loaded": 0, "matched": 0, "new_added": 0}

        with open(self.path, encoding="utf-8") as f:
            raw = json.load(f)

        # 过滤掉含 _comment key 的注释条目
        manual_records = [r for r in raw if "_comment" not in r]
        logger.info(f"加载手动分数：{len(manual_records)} 条记录")

        stats = {"loaded": len(manual_records), "matched": 0, "new_added": 0}

        for record in manual_records:
            matched_paper = self._find_match(record, papers)

            if matched_paper:
                self._write_scores(matched_paper, record, domain)
                stats["matched"] += 1
                logger.debug(f"手动分数写入（匹配）：{matched_paper.title[:60]}")
            else:
                new_paper = self._create_paper(record, domain)
                papers.append(new_paper)
                stats["new_added"] += 1
                logger.debug(f"手动新增论文：{record.get('title', '')[:60]}")

        logger.info(
            f"手动导入完成：匹配 {stats['matched']} 篇，"
            f"新增 {stats['new_added']} 篇"
        )
        return papers, stats

    def _find_match(
        self, record: dict, papers: list[PaperRecord]
    ) -> Optional[PaperRecord]:
        """在现有列表中查找与 record 匹配的论文。"""
        arxiv_id = record.get("arxiv_id", "").strip()

        # 优先：arXiv ID 精确匹配
        if arxiv_id:
            for p in papers:
                if p.arxiv_id and p.arxiv_id.strip() == arxiv_id:
                    return p

        # 次选：标题相似度匹配
        record_title = record.get("title", "").lower().strip()
        if not record_title:
            return None

        best_score = 0.0
        best_paper = None
        for p in papers:
            if not p.title:
                continue
            sim = SequenceMatcher(
                None, record_title, p.title.lower().strip()
            ).ratio()
            if sim > best_score:
                best_score = sim
                best_paper = p

        if best_score >= self.TITLE_SIMILARITY_THRESHOLD:
            return best_paper
        return None

    def _write_scores(
        self, paper: PaperRecord, record: dict, domain: str
    ) -> None:
        """将手动记录的分数写入已存在的 PaperRecord。"""
        from config.knowledge_base import DOMAIN_KNOWLEDGE_BASE
        domain_info = DOMAIN_KNOWLEDGE_BASE.get(domain, {})
        valid_datasets = domain_info.get("datasets", [])

        for dataset, metrics in record.get("scores", {}).items():
            if valid_datasets and dataset not in valid_datasets:
                logger.warning(f"未知数据集：{dataset}，跳过")
                continue

            score_obj = MetricScores(confidence=ExtractionConfidence.MANUAL)
            for metric, val in metrics.items():
                if hasattr(score_obj, metric) and isinstance(val, (int, float)):
                    setattr(score_obj, metric, float(val))
            paper.scores[dataset] = score_obj

        paper.scores_extracted = bool(paper.scores)

        # 补充元数据（如果原来为空）
        for field in ["paper_url", "code_url", "venue", "year", "ccf_rank", "sci_tier"]:
            if not getattr(paper, field, None) and record.get(field):
                setattr(paper, field, record[field])

    def _create_paper(self, record: dict, domain: str) -> PaperRecord:
        """根据手动记录新建 PaperRecord。"""
        from shared.models import PaperSource
        paper = PaperRecord(
            paper_id=f"manual_{record.get('arxiv_id', '') or record.get('title', '')[:20]}",
            title=record.get("title", ""),
            arxiv_id=record.get("arxiv_id", "") or None,
            year=record.get("year"),
            venue=record.get("venue"),
            ccf_rank=record.get("ccf_rank"),
            sci_tier=record.get("sci_tier"),
            paper_url=record.get("paper_url"),
            code_url=record.get("code_url"),
            found_by=[PaperSource.MANUAL],
        )
        self._write_scores(paper, record, domain)
        return paper
