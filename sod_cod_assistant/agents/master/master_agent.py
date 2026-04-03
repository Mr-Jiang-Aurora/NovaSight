"""
主控 Agent —— 完整重写版
修复：数据流、分段报告生成、强制执行模式、输出路径记录
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from shared.models import SharedContext, MasterReport, WorkflowPlan
from agents.master.shared_context       import SharedContextManager
from agents.master.workflow_planner     import WorkflowPlanner
from agents.master.context_bridge       import ContextBridge
from agents.master.synthesis_generator  import SynthesisGenerator

logger = logging.getLogger(__name__)


class MasterAgent:
    """主控调度 Agent（完整重写版）"""

    def __init__(self, settings):
        self.settings    = settings
        self.ctx_mgr     = SharedContextManager()
        self.planner     = WorkflowPlanner()
        self.bridge      = ContextBridge()
        self.synthesizer = SynthesisGenerator(settings)

    async def run(
        self,
        domain:            str  = "COD",
        github_url:        Optional[str]  = None,
        uploaded_files:    Optional[dict] = None,
        local_dir:         Optional[str]  = None,
        arch_image_path:   Optional[str]  = None,
        visual_image_path: Optional[str]  = None,
        user_method_desc:  str  = "",
        force_agent1:      bool = False,
        force_all:         bool = False,
    ) -> MasterReport:
        start_time = time.time()

        # ── 1. 初始化 SharedContext ─────────────────────────────────
        ctx = self.ctx_mgr.create(
            domain            = domain,
            github_url        = github_url,
            uploaded_files    = uploaded_files or {},
            local_dir         = local_dir,
            arch_image_path   = arch_image_path,
            visual_image_path = visual_image_path,
            user_method_desc  = user_method_desc,
        )

        logger.info("=" * 60)
        logger.info(f"[Master] 启动，session={ctx.session_id}，域={domain}")
        logger.info(f"[Master] 代码输入：{'GitHub=' + github_url if github_url else '无'}")
        logger.info(f"[Master] 图片输入：arch={arch_image_path}, visual={visual_image_path}")
        logger.info(f"[Master] force_all={force_all}")
        logger.info("=" * 60)

        # ── 2. 工作流规划 ───────────────────────────────────────────
        plan = self.planner.plan(ctx, force_all=force_all)
        logger.info(f"[Master] 工作流：{plan.reason}")

        agents_run  = []
        all_outputs = {}

        # ── 3. Agent1：SOTA 搜索 ─────────────────────────────────────
        logger.info("\n[Master] ─── 阶段1：Agent1 SOTA搜索 ─────────────────")
        a1_paths = await self._run_agent1(ctx, force=force_agent1 or force_all)
        if ctx.agent1_done:
            agents_run.append("Agent1")
            all_outputs["agent1"] = a1_paths
            logger.info(f"[Master] Agent1 完成，输出：{a1_paths}")
        else:
            logger.error(f"[Master] Agent1 失败：{ctx.agent1_error}")

        # ── 4. Agent2：指标诊断 ─────────────────────────────────────
        logger.info("\n[Master] ─── 阶段2：Agent2 指标诊断 ───────────────────")
        if ctx.leaderboard:
            a2_paths = await self._run_agent2(ctx)
            if ctx.agent2_done:
                agents_run.append("Agent2")
                all_outputs["agent2"] = a2_paths
                logger.info(f"[Master] Agent2 完成，输出：{a2_paths}")
            else:
                logger.error(f"[Master] Agent2 失败：{ctx.agent2_error}")
        else:
            logger.warning("[Master] Agent2 跳过：无 leaderboard 数据")

        # ── 5. Agent4：图像分析（在 Agent3 之前）──────────────────
        if plan.run_agent4 and plan.agent4_mode != "none":
            logger.info("\n[Master] ─── 阶段3：Agent4 图像分析 ──────────────────")
            # TASK3：把 Agent2 SOTA 摘要注入 Agent4，用于创新性评估
            a4_paths = await self._run_agent4(ctx)
            if ctx.agent4_done:
                agents_run.append("Agent4")
                all_outputs["agent4"] = a4_paths
                logger.info(f"[Master] Agent4 ✅ 输出：{list(a4_paths.keys())}")
                logger.info(f"[Master] structure_hint 长度：{len(ctx.structure_hint)} 字")
            else:
                logger.error(f"[Master] Agent4 失败：{ctx.agent4_error}")

        # ── 6. Agent3：代码分析 ─────────────────────────────────────
        if plan.run_agent3:
            logger.info("\n[Master] ─── 阶段4：Agent3 代码分析 ──────────────────")
            a3_paths = await self._run_agent3(ctx)
            if ctx.agent3_done:
                agents_run.append("Agent3")
                all_outputs["agent3"] = a3_paths
                logger.info(f"[Master] Agent3 ✅ 输出：{list(a3_paths.keys())}")
            else:
                logger.error(f"[Master] Agent3 失败：{ctx.agent3_error}")

        # ── 6.5 TASK2：架构-代码双向验证 ──────────────────────────
        if ctx.agent3_done and ctx.agent4_done:
            logger.info("\n[Master] ─── 额外：架构-代码双向验证 ──────────────────────")
            try:
                from agents.master.arch_code_validator import ArchCodeValidator
                from config.settings import get_agent_output_dir
                from datetime import datetime

                arch_hint     = getattr(ctx.agent4_report, "arch_hint", None)
                code_analysis = getattr(ctx.agent3_report, "analysis", None)

                if arch_hint and code_analysis and arch_hint.key_modules:
                    validator  = ArchCodeValidator()
                    val_report = validator.validate(arch_hint, code_analysis)
                    ctx.validation_report = val_report

                    out_dir  = Path(get_agent_output_dir(4))
                    out_dir.mkdir(parents=True, exist_ok=True)
                    val_ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                    val_path = out_dir / f"arch_code_validation_{val_ts}.md"

                    from agents.agent4_vision.vision_report_writer import VisionReportWriter
                    VisionReportWriter()._write_validation_md(val_report, val_path)
                    all_outputs["validation"] = str(val_path)
                    logger.info(
                        f"[Master] 双向验证完成：一致性={val_report.consistency_score}%，"
                        f"报告={val_path.name}"
                    )
                else:
                    logger.info("[Master] 双向验证跳过：arch_hint 或 code_analysis 为空")
            except Exception as e:
                logger.error(f"[Master] 双向验证失败（不影响主流程）：{e}")

        # ── 7. 综合报告（分段生成）────────────────────────────────
        logger.info("\n[Master] ─── 阶段5：综合报告生成（分段）─────────────────")
        narrative_parts = await self.synthesizer.generate_segmented(ctx)
        full_narrative  = "\n\n".join(narrative_parts)
        ctx.master_narrative = full_narrative

        # ── 8. 写出最终报告 ─────────────────────────────────────────
        total_time    = time.time() - start_time
        master_report = MasterReport(
            session_id      = ctx.session_id,
            domain          = domain,
            agents_run      = agents_run,
            total_time_s    = round(total_time, 1),
            narrative       = full_narrative,
            all_sub_outputs = all_outputs,
        )
        output_paths             = self._write_master_outputs(ctx, master_report)
        master_report.output_paths = output_paths
        ctx.output_paths           = output_paths
        self.ctx_mgr.save(ctx)

        logger.info(f"\n[Master] 全流程完成")
        logger.info(f"  执行 Agent：{', '.join(agents_run)}")
        logger.info(f"  总耗时：{total_time:.1f}s")
        logger.info(f"  报告字数：{len(full_narrative)} 字")
        logger.info(f"  报告路径：{output_paths.get('markdown', '-')}")

        return master_report

    # ── Agent 执行方法 ───────────────────────────────────────────

    async def _run_agent1(self, ctx: SharedContext, force: bool) -> dict:
        """Agent1：SOTA 搜索（用缓存 or 重新运行）"""
        if not force:
            self.bridge.collect_agent1_outputs(ctx)
            if ctx.leaderboard:
                ctx.agent1_done = True
                logger.info(
                    f"[Agent1] 从缓存加载：{ctx.leaderboard.total_papers} 篇"
                )
                return {"source": "cache"}

        try:
            from agents.agent1_sota.agent1_main import Agent1SOTAAgent
            from shared.models import SOTALeaderboard
            agent1  = Agent1SOTAAgent(self.settings)
            papers  = await agent1.run(domain=ctx.domain)
            ctx.leaderboard = SOTALeaderboard(
                domain          = ctx.domain,
                papers          = papers,
                total_papers    = len(papers),
                search_completed= True,
                fetch_completed = True,
                parse_completed = True,
            )
            ctx.agent1_done = True
            logger.info(f"[Agent1] 搜索完成：{len(papers)} 篇")

            from config.settings import get_agent_output_dir
            agent1_dir   = Path(get_agent_output_dir(1))
            output_paths = {}
            for f in list(agent1_dir.glob("*.json")) + list(agent1_dir.glob("*.md")):
                output_paths[f.stem] = str(f)
            return output_paths
        except Exception as e:
            ctx.agent1_error = str(e)
            logger.error(f"[Agent1] 失败：{e}")
            self.bridge.collect_agent1_outputs(ctx)
            if ctx.leaderboard:
                ctx.agent1_done = True
                logger.warning("[Agent1] 降级到历史缓存")
            return {}

    async def _run_agent2(self, ctx: SharedContext) -> dict:
        """Agent2：指标诊断"""
        try:
            from agents.agent2_gap.agent2_main import Agent2
            agent2 = Agent2(self.settings)
            report = await agent2.run(
                leaderboard        = ctx.leaderboard,
                domain             = ctx.domain,
                generate_narrative = True,
                user_method_desc   = ctx.user_method_desc,
            )
            ctx.agent2_report  = report
            ctx.agent2_summary = self.bridge.extract_agent2_summary(ctx)
            ctx.agent2_done    = True

            output_paths = getattr(report, "output_paths", {}) or {}
            return output_paths
        except Exception as e:
            ctx.agent2_error = str(e)
            logger.error(f"[Agent2] 失败：{e}")
            return {}

    async def _run_agent3(self, ctx: SharedContext) -> dict:
        """Agent3：代码分析"""
        try:
            from agents.agent3_code.agent3_main import Agent3
            agent3 = Agent3(self.settings)
            kwargs = self.bridge.build_agent3_kwargs(ctx)
            report = await agent3.run(**kwargs)
            ctx.agent3_report = report
            analysis = getattr(report, "analysis", None)
            if analysis and getattr(analysis, "arch_summary", ""):
                ctx.agent3_summary = analysis.arch_summary[:500]
            ctx.agent3_done = True

            output_paths = getattr(report, "output_paths", {}) or {}
            return output_paths
        except Exception as e:
            ctx.agent3_error = str(e)
            logger.error(f"[Agent3] 失败：{e}")
            return {}

    async def _run_agent4(self, ctx: SharedContext) -> dict:
        """Agent4：图像分析"""
        try:
            from agents.agent4_vision.agent4_main import Agent4
            agent4 = Agent4(self.settings)
            kwargs = self.bridge.build_agent4_kwargs(ctx)
            # TASK3：注入 Agent2 SOTA 摘要供创新性评估使用
            kwargs["sota_context"] = ctx.agent2_summary or ""
            report = await agent4.run(**kwargs)
            ctx.agent4_report  = report
            ctx.structure_hint = self.bridge.extract_structure_hint(ctx)
            ctx.agent4_done    = True

            output_paths = getattr(report, "output_paths", {}) or {}
            return output_paths
        except Exception as e:
            ctx.agent4_error = str(e)
            logger.error(f"[Agent4] 失败：{e}")
            return {}

    def _write_master_outputs(
        self, ctx: SharedContext, report: MasterReport
    ) -> dict:
        """写出主控报告文件"""
        from config.settings import get_agent_output_dir

        out_dir = Path(get_agent_output_dir(0))
        out_dir.mkdir(parents=True, exist_ok=True)
        sid   = ctx.session_id
        paths = {}

        # 主报告 Markdown
        md_path = out_dir / f"master_report_{sid}.md"
        header  = (
            f"# {ctx.domain} 综合研究诊断报告\n\n"
            f"| 项目 | 内容 |\n"
            f"|:---|:---|\n"
            f"| 生成时间 | {report.generated_at.strftime('%Y-%m-%d %H:%M')} |\n"
            f"| 研究领域 | {ctx.domain} |\n"
            f"| 执行 Agent | {', '.join(report.agents_run)} |\n"
            f"| 总耗时 | {report.total_time_s}s |\n"
            f"| 报告字数 | {len(report.narrative)} 字 |\n\n"
            f"---\n\n"
        )
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(header + report.narrative)
        paths["markdown"] = str(md_path)

        # 结构化 JSON
        json_path = out_dir / f"master_report_{sid}.json"
        json_data = {
            "meta": {
                "session_id":   sid,
                "domain":       ctx.domain,
                "generated_at": report.generated_at.isoformat(),
                "agents_run":   report.agents_run,
                "total_time_s": report.total_time_s,
                "word_count":   len(report.narrative),
            },
            "sections": self._extract_sections(report.narrative),
            "all_sub_outputs": report.all_sub_outputs,
            "agent_status": {
                "agent1": {"done": ctx.agent1_done, "error": ctx.agent1_error},
                "agent2": {"done": ctx.agent2_done, "error": ctx.agent2_error},
                "agent3": {"done": ctx.agent3_done, "error": ctx.agent3_error},
                "agent4": {"done": ctx.agent4_done, "error": ctx.agent4_error},
            },
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)
        paths["json"] = str(json_path)

        size_kb = md_path.stat().st_size // 1024
        logger.info(f"[Master] 报告已写出：{md_path}（{size_kb} KB）")
        return paths

    def _extract_sections(self, narrative: str) -> dict:
        """从 Markdown 报告中提取各章节内容"""
        import re
        sections = {}
        parts    = re.split(r'\n## ', narrative)
        for i, part in enumerate(parts):
            if i == 0:
                sections["preamble"] = part.strip()
            else:
                lines      = part.strip().splitlines()
                title_line = lines[0] if lines else f"section_{i}"
                content    = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
                key        = re.sub(r'[^\w\u4e00-\u9fff]', '_', title_line[:30])
                sections[key] = f"## {title_line}\n\n{content}"
        return sections
