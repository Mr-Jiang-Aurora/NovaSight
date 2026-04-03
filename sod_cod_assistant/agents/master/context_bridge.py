"""
Agent 间数据传递适配器
负责将一个 Agent 的输出转化为下一个 Agent 需要的输入格式。
"""

import json
import logging
from pathlib import Path
from shared.models import SharedContext

logger = logging.getLogger(__name__)


class ContextBridge:
    """Agent 间数据传递适配器"""

    # ── Agent2 摘要提取 ─────────────────────────────────────────────

    def extract_agent2_summary(self, ctx: SharedContext) -> str:
        """
        从 Agent2 报告中提取精简摘要，供 Agent3 和 Agent4 使用。
        优先读取已缓存的 summary 字符串，其次从报告对象中提取。
        """
        if ctx.agent2_summary:
            return ctx.agent2_summary

        if ctx.agent2_report:
            report = ctx.agent2_report
            parts  = []

            # Top3 综合得分
            if hasattr(report, "profiles") and report.profiles:
                sorted_p = sorted(
                    report.profiles,
                    key=lambda p: p.overall_score,
                    reverse=True,
                )[:3]
                top3 = ["当前 SOTA Top3（综合得分）："]
                for i, p in enumerate(sorted_p, 1):
                    score_str = f"{p.overall_score:.4f}" if p.overall_score is not None else "?"
                    top3.append(
                        f"  {i}. {p.title[:40]} [{p.venue or '-'},{p.year or '-'}]"
                        f" 得分={score_str}"
                    )
                parts.append("\n".join(top3))

            # COD10K 饱和度
            if hasattr(report, "gap_analyses") and report.gap_analyses:
                for ga in report.gap_analyses:
                    if ga.dataset == "COD10K":
                        sat = [f"COD10K 指标饱和度："]
                        for metric, status in ga.saturation.items():
                            gap = ga.current_range.get(metric, 0)
                            gap_str = f"{gap:.4f}" if gap is not None else "?"
                            sat.append(
                                f"  {metric}: {status}，方法间差距={gap_str}"
                            )
                        parts.append("\n".join(sat))
                        break

            # narrative 摘要
            if hasattr(report, "narrative") and report.narrative:
                parts.append(
                    f"诊断报告摘要：\n{report.narrative[:800]}..."
                )

            ctx.agent2_summary = "\n\n".join(parts)

        return ctx.agent2_summary

    # ── structure_hint 提取（Agent4 → Agent3）───────────────────────

    def extract_structure_hint(self, ctx: SharedContext) -> str:
        """
        从 Agent4 输出中提取 structure_hint，供 Agent3 使用。

        读取优先级：
          1. ctx.structure_hint（已缓存）
          2. ctx.agent4_report.structure_hint_for_agent3
          3. cache/agent4/**/arch_hint_full_*.json 的 structure_hint 字段（最完整）
          4. cache/agent4/**/arch_hint_*.txt（纯文本备份）
        """
        if ctx.structure_hint:
            return ctx.structure_hint

        if ctx.agent4_report:
            hint = ctx.agent4_report.structure_hint_for_agent3
            if hint:
                ctx.structure_hint = hint
                return hint

        # 从文件读取：优先 arch_hint_full JSON（structure_hint 最完整）
        agent4_dir = Path("cache/agent4")
        if agent4_dir.exists():
            full_files = sorted(
                agent4_dir.rglob("arch_hint_full_*.json"), reverse=True
            )
            if full_files:
                try:
                    with open(full_files[0], encoding="utf-8") as f:
                        data = json.load(f)
                    hint = data.get("structure_hint", "")
                    if hint:
                        logger.info(
                            f"[Bridge] structure_hint 从 {full_files[0].name} 读取"
                        )
                        ctx.structure_hint = hint
                        return hint
                except Exception as e:
                    logger.warning(f"[Bridge] 读取 arch_hint_full JSON 失败：{e}")

            # 再 fallback 到纯文本 arch_hint
            txt_files = sorted(
                agent4_dir.rglob("arch_hint_*.txt"), reverse=True
            )
            if txt_files:
                try:
                    ctx.structure_hint = txt_files[0].read_text(encoding="utf-8")
                    logger.info(
                        f"[Bridge] structure_hint 从 {txt_files[0].name} 读取"
                    )
                    return ctx.structure_hint
                except Exception as e:
                    logger.warning(f"[Bridge] 读取 arch_hint txt 失败：{e}")

        return ""

    # ── Agent3 / Agent4 参数构建 ─────────────────────────────────────

    def build_agent3_kwargs(self, ctx: SharedContext) -> dict:
        """构建调用 Agent3 所需的参数字典"""
        kwargs = {
            "agent2_summary": self.extract_agent2_summary(ctx),
            "structure_hint": self.extract_structure_hint(ctx),
            "domain":         ctx.domain,
            "use_claude":     True,
        }

        # local_dir 优先级高于其他模式
        if getattr(ctx, "local_dir", None):
            kwargs["local_dir"] = ctx.local_dir
            return kwargs

        plan = ctx.plan
        if not plan or plan.agent3_mode == "sota_only":
            # 无代码输入：传占位文件，Agent3 将仅基于 SOTA 数据给出建议
            kwargs["uploaded_files"] = {"placeholder.txt": b"no_code_provided"}
            return kwargs

        if plan.agent3_mode in ("github", "both"):
            kwargs["github_url"] = ctx.github_url
        if plan.agent3_mode in ("upload", "both"):
            kwargs["uploaded_files"] = ctx.uploaded_files

        return kwargs

    def build_agent4_kwargs(self, ctx: SharedContext) -> dict:
        """构建调用 Agent4 所需的参数字典"""
        kwargs = {}
        plan   = ctx.plan
        if plan:
            if plan.agent4_mode in ("arch", "both"):
                kwargs["arch_image_path"] = ctx.arch_image_path
                kwargs["arch_user_hint"]  = ctx.user_method_desc or ""
            if plan.agent4_mode in ("visual", "both"):
                kwargs["visual_image_path"]  = ctx.visual_image_path
                kwargs["visual_user_method"] = "Ours"
                kwargs["visual_user_hint"]   = ctx.user_method_desc or ""
        return kwargs

    # ── Agent1 缓存加载 ─────────────────────────────────────────────

    def collect_agent1_outputs(self, ctx: SharedContext) -> None:
        """
        从 Agent1 缓存文件加载 SOTALeaderboard，
        优先从今日缓存读取，避免重复搜索。
        """
        from pathlib import Path
        from shared.models import PaperRecord, SOTALeaderboard
        from config.settings import get_agent_output_dir

        # 先检查 Agent1 今日缓存
        agent1_today = Path(get_agent_output_dir(1))
        cache_files  = sorted(
            list(agent1_today.glob("fetch_result_*.json"))
            + list(agent1_today.glob("sota_ranking_*.json")),
            reverse=True,
        )

        # 再查历史缓存目录
        if not cache_files:
            agent1_dir = Path("cache") / "agent1"
            if agent1_dir.exists():
                cache_files = sorted(
                    agent1_dir.rglob(
                        f"fetch_result_{ctx.domain}*.json"
                    ),
                    reverse=True,
                )

        # 兜底：旧格式 cache/sota_cache/
        if not cache_files:
            legacy_dir = Path("cache") / "sota_cache"
            if legacy_dir.exists():
                cache_files = sorted(
                    list(legacy_dir.glob(f"fetch_result_{ctx.domain}*.json"))
                    + list(legacy_dir.glob(f"debug_search_{ctx.domain}*.json")),
                    reverse=True,
                )

        if not cache_files:
            logger.warning("[Master] 未找到 Agent1 缓存文件")
            return

        try:
            with open(cache_files[0], encoding="utf-8") as f:
                raw = json.load(f)
            # 兼容两种格式：list（旧）或 {"metadata":..., "papers":[...]}（新）
            if isinstance(raw, list):
                papers = [PaperRecord(**p) for p in raw]
            elif isinstance(raw, dict):
                papers_data = raw.get("papers", [])
                papers = [
                    PaperRecord(**p) if isinstance(p, dict) else p
                    for p in papers_data
                ]
            else:
                logger.warning(f"[Master] 未知缓存格式：{type(raw)}")
                return

            # 合并手动分数
            manual_path = Path("cache") / "manual_scores.json"
            if manual_path.exists():
                from agents.agent1_sota.cache.manual_scores_loader import (
                    ManualScoresLoader,
                )
                loader = ManualScoresLoader(str(manual_path))
                papers, _ = loader.load_and_merge(papers, ctx.domain)

            ctx.leaderboard = SOTALeaderboard(
                domain          = ctx.domain,
                papers          = papers,
                total_papers    = len(papers),
                search_completed= True,
                fetch_completed = True,
                parse_completed = True,
            )
            logger.info(
                f"[Master] Agent1 缓存加载完成：{len(papers)} 篇论文"
                f"（来自 {cache_files[0].name}）"
            )
        except Exception as e:
            ctx.agent1_error = str(e)
            logger.error(f"[Master] Agent1 缓存加载失败：{e}")
