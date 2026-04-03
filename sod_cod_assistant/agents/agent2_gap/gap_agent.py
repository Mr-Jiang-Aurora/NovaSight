"""
指标对比诊断 Agent - Gap Analysis Agent
Phase 2+ 将实现以下功能：
  1. 解析用户提供的模型指标（支持 JSON、CSV、手动输入）
  2. 从 SOTALeaderboard 中提取各 Top-N 模型的指标
  3. 逐数据集、逐指标计算差距（绝对差值 + 百分比）
  4. 识别差距模式：
     - 全局弱势（各项均落后 > 3%）
     - MAE 偏高（小目标检测能力不足）
     - Sm/Em 背离（全局结构 vs 局部精度不均衡）
  5. 基于差距模式生成结构化原因假设列表

本文件在 Phase 1 中仅作占位，不含实现代码。
"""


class GapAgent:
    """指标对比诊断 Agent（Phase 2+ 实现）"""
    pass
