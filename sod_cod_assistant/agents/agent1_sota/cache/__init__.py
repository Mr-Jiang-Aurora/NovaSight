"""
cache 包 - Agent1 第四层：缓存与增量更新层（Phase 4 实现）

缓存策略：
  首次运行（无缓存）：
    → 执行完整流程（Phase 1-3）
    → 保存结果到 sota_cache/{domain}.json
    → 保存 index.json（记录每个监控 venue 的最新年份）

  后续运行（有缓存）：
    → 读取 index.json
    → 通过 DBLP API 查询各 venue 最新期号
    → 有新内容 → 只对有更新的 venue 重新搜索+获取+解析
    → 无新内容 → 直接返回缓存（秒级响应）
    → 合并新论文到缓存，更新 index.json
"""

from .cache_manager import CacheManager
from .increment_checker import IncrementChecker
from .manual_scores_loader import ManualScoresLoader

__all__ = [
    "CacheManager",
    "IncrementChecker",
    "ManualScoresLoader",
]
