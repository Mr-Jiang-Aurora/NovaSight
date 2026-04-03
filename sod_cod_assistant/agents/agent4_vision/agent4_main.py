"""
Agent4 主入口：图像识别分析（双模式）
"""

import logging
from typing import Optional

from shared.models import Agent4Report

logger = logging.getLogger(__name__)


class Agent4:
    """图像识别分析 Agent（双模式）"""

    def __init__(self, settings):
        self.settings = settings

    async def run(
        self,
        arch_image_path:    Optional[str]   = None,
        arch_image_bytes:   Optional[bytes] = None,
        visual_image_path:  Optional[str]   = None,
        visual_image_bytes: Optional[bytes] = None,
        arch_user_hint:     str = "",
        visual_user_method: str = "",
        visual_user_hint:   str = "",
        sota_context:       str = "",   # Agent2 传来的 SOTA 摘要（TASK3 用）
    ) -> Agent4Report:
        """
        Agent4 主入口，支持双模式。

        调用示例：
          # 模式1：分析架构图
          report = await agent4.run(arch_image_path="my_arch.png")

          # 模式2：分析对比图
          report = await agent4.run(
              visual_image_path="compare.png",
              visual_user_method="Ours"
          )

          # 两种模式同时使用
          report = await agent4.run(
              arch_image_path="arch.png",
              visual_image_path="compare.png",
              visual_user_method="Ours"
          )
        """
        from agents.agent4_vision.image_loader       import ImageLoader
        from agents.agent4_vision.arch_analyzer      import ArchAnalyzer
        from agents.agent4_vision.visual_comparator  import VisualComparator
        from agents.agent4_vision.vision_report_writer import VisionReportWriter

        loader     = ImageLoader()
        arch_ana   = ArchAnalyzer(self.settings)
        # 注入 SOTA 上下文供创新性评估使用（TASK3）
        arch_ana._sota_context = sota_context
        # 注入 Semantic Scholar API Key（TASK1，可选）
        arch_ana._semantic_scholar_api_key = getattr(
            self.settings, "SEMANTIC_SCHOLAR_API_KEY", ""
        )
        visual_ana = VisualComparator(self.settings)
        writer     = VisionReportWriter()

        report = Agent4Report()
        modes  = []

        # ── 模式1：架构图解析 ─────────────────────────────────────────
        if arch_image_path or arch_image_bytes:
            modes.append("arch")
            if arch_image_path:
                img = loader.load_from_path(arch_image_path)
            else:
                img = loader.load_from_bytes(arch_image_bytes, "arch.png")

            if img:
                logger.info("[Agent4] 开始架构图解析...")
                hint = arch_ana.analyze(img, arch_user_hint)
                report.arch_hint = hint
                report.structure_hint_for_agent3 = hint.structure_hint
                logger.info(
                    f"[Agent4] 架构图解析完成，置信度：{hint.confidence}"
                )
            else:
                logger.error("[Agent4] 架构图加载失败")

        # ── 模式2：可视化对比分析 ─────────────────────────────────────
        if visual_image_path or visual_image_bytes:
            modes.append("visual")
            if visual_image_path:
                img = loader.load_from_path(visual_image_path)
            else:
                img = loader.load_from_bytes(visual_image_bytes, "visual.png")

            if img:
                logger.info("[Agent4] 开始可视化对比分析...")
                va = visual_ana.analyze(img, visual_user_method, visual_user_hint)
                report.visual = va

                if va.key_findings:
                    report.summary_for_agent2 = (
                        "视觉对比定性分析补充：\n"
                        + "\n".join(f"- {f}" for f in va.key_findings)
                        + (f"\n- 用户方法排名：第 {va.user_method_rank} 名"
                           if va.user_method_rank else "")
                    )
                logger.info(
                    f"[Agent4] 可视化分析完成，识别 {va.image_count} 列方法"
                )
            else:
                logger.error("[Agent4] 对比图加载失败")

        report.mode   = "+".join(modes) if modes else "none"
        report.status = "success" if modes else "failed"

        writer.write_all(report)
        logger.info(f"[Agent4] 完成，模式：{report.mode}")
        return report
