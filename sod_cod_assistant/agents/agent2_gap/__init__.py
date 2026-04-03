"""
agent2_gap 包 - 指标对比诊断 Agent

功能：
  A. 多维度排行榜（每数据集 × 每指标 × 每 CCF 分层）
  B. 差距分析（历年 SOTA 变化趋势）
  C. 方法强弱特征画像（哪个指标强/弱）
  D. 年度进步率分析（饱和度判断）
  E. 综合得分排名（复现 Excel 公式）
  F. 自然语言诊断报告（调用 Claude API）
"""

from .agent2_main import Agent2

__all__ = ["Agent2"]
