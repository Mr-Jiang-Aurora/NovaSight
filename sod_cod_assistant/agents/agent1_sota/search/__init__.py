"""
search 包 - Agent1 第一层：搜索层（Phase 1 完整实现）

四路并行搜索架构：
    SemanticScholarSearcher  - 关键词搜索 + 引用图谱扩展
    OpenAlexSearcher         - 语义搜索 + cursor 分页
    DBLPSearcher             - stream 查询按期刊/会议遍历
    CVFSearcher              - CVF Open Access HTML 爬取

调度入口：
    SearchOrchestrator.run_search(domain) → List[PaperRecord]
"""

from .base_searcher import BaseSearcher
from .semantic_scholar import SemanticScholarSearcher
from .openalex import OpenAlexSearcher
from .dblp import DBLPSearcher
from .cvf_open_access import CVFSearcher
from .deduplicator import PaperDeduplicator
from .search_orchestrator import SearchOrchestrator

__all__ = [
    "BaseSearcher",
    "SemanticScholarSearcher",
    "OpenAlexSearcher",
    "DBLPSearcher",
    "CVFSearcher",
    "PaperDeduplicator",
    "SearchOrchestrator",
]
