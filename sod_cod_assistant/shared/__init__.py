"""
shared 包 - 跨 Agent 共用模块

导出：
    models  - Pydantic 数据模型（PaperRecord, SearchResult, SOTALeaderboard 等）
    utils   - 通用工具函数（标题归一化、日志初始化等）
"""

from shared import models
from shared import utils

__all__ = ["models", "utils"]
