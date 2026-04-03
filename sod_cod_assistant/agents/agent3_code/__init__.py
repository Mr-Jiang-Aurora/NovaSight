"""
agent3_code 包 - 用户代码架构分析 Agent（双输入模式）

功能：
  - 模式A：从 GitHub 链接拉取用户代码
  - 模式B：读取用户本地上传文件（.py / zip）
  - 静态分析架构组件、损失函数、训练配置
  - 调用 Claude API 生成语义理解和改进建议
  - 结合 Agent2 SOTA 数据进行差距分析
"""

from agents.agent3_code.agent3_main import Agent3

__all__ = ["Agent3"]
