"""
agent4_vision 包 - 图像识别分析 Agent（双模式）

模式1：架构图解析 → 生成 structure_hint 传给 Agent3
模式2：可视化对比图分析 → 定性评分 + 关键发现
"""

from agents.agent4_vision.agent4_main import Agent4

__all__ = ["Agent4"]
