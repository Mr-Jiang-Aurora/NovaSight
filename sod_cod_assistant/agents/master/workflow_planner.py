"""
工作流规划器
根据用户输入自动决定执行哪些 Agent，以什么顺序执行。
"""

import logging
from shared.models import WorkflowPlan, SharedContext

logger = logging.getLogger(__name__)


class WorkflowPlanner:
    """工作流规划器"""

    def plan(self, ctx: SharedContext, force_all: bool = False) -> WorkflowPlan:
        """
        根据 SharedContext 生成工作流计划。
        force_all=True 时强制所有 Agent 都运行（调试用）。
        """
        plan    = WorkflowPlan()
        reasons = []

        plan.run_agent1 = True
        plan.run_agent2 = True
        reasons.append("Agent1+2 始终运行")

        # Agent4 判断
        has_arch   = bool(ctx.arch_image_path)
        has_visual = bool(ctx.visual_image_path)
        if force_all or has_arch or has_visual:
            plan.run_agent4 = True
            if has_arch and has_visual:
                plan.agent4_mode = "both"
            elif has_arch:
                plan.agent4_mode = "arch"
            elif has_visual:
                plan.agent4_mode = "visual"
            else:
                plan.agent4_mode = "none"  # force_all 但无图片，跳过实际调用
            reasons.append(f"Agent4: {plan.agent4_mode}")

        # Agent3 判断
        has_github    = bool(ctx.github_url)
        has_upload    = bool(ctx.uploaded_files)
        has_local_dir = bool(getattr(ctx, "local_dir", None))
        if force_all or has_github or has_upload or has_local_dir:
            plan.run_agent3 = True
            if has_local_dir:
                plan.agent3_mode = "local_dir"
            elif has_github and has_upload:
                plan.agent3_mode = "both"
            elif has_github:
                plan.agent3_mode = "github"
            elif has_upload:
                plan.agent3_mode = "upload"
            else:
                plan.agent3_mode = "sota_only"  # force_all 但无代码：仅基于 SOTA 给建议
            reasons.append(f"Agent3: {plan.agent3_mode}")

        plan.reason = "；".join(reasons)
        logger.info(f"[Master] 工作流规划完成：{plan.reason}")

        ctx.plan = plan
        return plan
