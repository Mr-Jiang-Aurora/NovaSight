"""
agent1_sota 包 - SOTA 调研 Agent（Phase 1 搜索层完整实现）

四层管线架构：
    第一层  search/    搜索层  → 四源并联发现论文         ✅ Phase 1 已实现
    第二层  fetcher/   获取层  → PDF 五级瀑布流下载       🔜 Phase 2
    第三层  parser/    解析层  → 两阶段表格定位与提取     🔜 Phase 3
    第四层  cache/     缓存层  → 增量更新管理             🔜 Phase 4

主入口：
    from agents.agent1_sota.agent1_main import Agent1SOTAAgent
    agent = Agent1SOTAAgent()
    papers = await agent.run(domain="COD")
"""

from agents.agent1_sota.agent1_main import Agent1SOTAAgent

__all__ = ["Agent1SOTAAgent"]
