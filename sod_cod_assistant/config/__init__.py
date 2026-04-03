"""
config 包 - 项目配置与领域知识库

导出：
    settings     - 全局配置单例（从 .env 读取）
    knowledge_base - 领域知识库（数据集、指标、期刊信息）
"""

from config.settings import settings
from config import knowledge_base

__all__ = ["settings", "knowledge_base"]
