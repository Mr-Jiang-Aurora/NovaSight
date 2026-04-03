"""Agent4 报告输出器"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from shared.models import Agent4Report

if TYPE_CHECKING:
    from shared.models import FigureTraceResult, ArchCodeValidationReport

logger = logging.getLogger(__name__)


class VisionReportWriter:
    """Agent4 报告输出器"""

    def write_all(
        self, report: Agent4Report, output_dir: str = ""
    ) -> dict[str, str]:
        from config.settings import get_agent_output_dir
        out = Path(get_agent_output_dir(4))
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        paths = {}

        if report.arch_hint:
            # 模式1：输出 structure_hint 文本（供 Agent3 读取）
            hint_path = out / f"arch_hint_{ts}.txt"
            with open(hint_path, "w", encoding="utf-8") as f:
                f.write(report.structure_hint_for_agent3)
            paths["arch_hint"] = str(hint_path)

            # 输出详细 JSON（arch_analysis_*.json）：完整原始 Claude 结构化响应
            json_path = out / f"arch_analysis_{ts}.json"
            hint = report.arch_hint
            if hint.raw_data:
                save_data = dict(hint.raw_data)
                save_data["_meta"] = {
                    "image_path":     hint.image_path,
                    "confidence":     hint.confidence,
                    "structure_hint": hint.structure_hint,
                }
            else:
                save_data = hint.model_dump(exclude={"raw_data"})
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            paths["arch_json"] = str(json_path)

            # 额外保存 arch_hint_full_{ts}.json：
            # context_bridge.extract_structure_hint 优先读取此文件的 structure_hint 字段
            full_path = out / f"arch_hint_full_{ts}.json"
            full_data = {
                "structure_hint": hint.structure_hint,
                "backbone":       hint.backbone,
                "decoder_type":   hint.decoder_type,
                "confidence":     hint.confidence,
                "key_modules":    hint.key_modules,
                "file_hints":     hint.file_hints,
                "data_flow":      hint.data_flow,
                "notes":          hint.notes,
                "image_path":     hint.image_path,
            }
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(full_data, f, ensure_ascii=False, indent=2)
            paths["arch_hint_full"] = str(full_path)
            logger.info(f"架构图分析已保存：{hint_path}，完整 JSON：{full_path}")

            # TASK1：Figure 溯源报告
            if report.arch_hint and report.arch_hint.trace_result:
                trace = report.arch_hint.trace_result
                trace_path = out / f"figure_trace_{ts}.md"
                self._write_trace_md(trace, trace_path)
                paths["figure_trace"] = str(trace_path)
                logger.info(f"Figure 溯源报告已保存：{trace_path}")

            # 架构图深度分析 Markdown 报告（供 UI 展示）
            arch_md_path = out / f"arch_analysis_{ts}.md"
            self._write_arch_analysis_md(hint, arch_md_path)
            paths["arch_analysis_md"] = str(arch_md_path)
            logger.info(f"架构图分析报告已保存：{arch_md_path}")

            # TASK3：创新性评估报告
            if report.arch_hint and report.arch_hint.innovation_evaluation:
                inno_path = out / f"innovation_evaluation_{ts}.md"
                with open(inno_path, "w", encoding="utf-8") as f:
                    f.write(
                        "# 学术创新性评估报告\n\n"
                        + report.arch_hint.innovation_evaluation
                    )
                paths["innovation"] = str(inno_path)
                logger.info(f"创新性评估已保存：{inno_path}")

        if report.visual:
            # 模式2：输出可视化分析 Markdown
            md_path = out / f"visual_analysis_{ts}.md"
            self._write_visual_md(report, md_path)
            paths["visual_md"] = str(md_path)

            json_path = out / f"visual_analysis_{ts}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(
                    report.visual.model_dump(),
                    f, ensure_ascii=False, indent=2
                )
            paths["visual_json"] = str(json_path)
            logger.info(f"可视化分析已保存：{md_path}")

        return paths

    def _write_visual_md(self, report: Agent4Report, path: Path) -> None:
        va = report.visual
        lines = [
            "# 预测结果可视化对比分析",
            f"**生成时间**：{report.generated_at.strftime('%Y-%m-%d %H:%M')}  ",
            f"**图像规模**：{va.row_count} 行 x {va.image_count} 列",
            "",
            "## 一、评分总览",
            "",
            "| 方法 | 边缘锐利度 | 背景干净度 | 目标完整性 | 形状准确度 | 综合 |",
            "|:--|:--:|:--:|:--:|:--:|:--:|",
        ]

        for col in va.columns:
            if col.method_name in ("Input", "GT", ""):
                continue
            if not any([col.edge_sharpness, col.bg_cleanliness,
                        col.target_completeness, col.shape_accuracy]):
                continue
            total = (col.edge_sharpness + col.bg_cleanliness
                     + col.target_completeness + col.shape_accuracy)
            lines.append(
                f"| {col.method_name} | {col.edge_sharpness}/5 | "
                f"{col.bg_cleanliness}/5 | {col.target_completeness}/5 | "
                f"{col.shape_accuracy}/5 | **{total}/20** |"
            )

        lines += [
            "",
            f"**综合最优**：{va.best_method}  ",
            f"**综合最差**：{va.worst_method}  ",
        ]
        if va.user_method_rank:
            lines.append(f"**用户方法排名**：第 {va.user_method_rank} 名  ")
        lines.append("")

        lines += ["## 二、逐方法分析", ""]
        for col in va.columns:
            if col.method_name in ("Input", "GT", "") or not col.overall_desc:
                continue
            lines += [f"### {col.method_name}", ""]
            lines.append(col.overall_desc)
            if col.strengths:
                lines.append(f"**优势**：{', '.join(col.strengths)}")
            if col.weaknesses:
                lines.append(f"**劣势**：{', '.join(col.weaknesses)}")
            lines.append("")

        if va.key_findings:
            lines += ["## 三、关键发现", ""]
            for finding in va.key_findings:
                lines.append(f"- {finding}")
            lines.append("")

        if va.improvement_focus:
            lines += ["## 四、改进建议", "", va.improvement_focus, ""]

        if report.summary_for_agent2:
            lines += [
                "## 五、传递给 Agent2 的补充信息",
                "",
                report.summary_for_agent2,
            ]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # ── 架构图深度分析 MD ─────────────────────────────────────────────

    def _write_arch_analysis_md(self, hint, path: Path) -> None:
        """将架构图分析结果（ArchHint）输出为可读 Markdown 报告"""
        lines = [
            "# 架构图深度分析报告",
            "",
            "## 总体架构概述",
            "",
            f"**主干网络（Backbone）**：{hint.backbone or '未识别'}",
            f"**解码器类型（Decoder）**：{hint.decoder_type or '未识别'}",
            f"**分析置信度**：{hint.confidence or '未知'}",
            "",
        ]

        if hint.structure_hint:
            lines += [
                "## 架构结构详述",
                "",
                hint.structure_hint,
                "",
            ]

        # key_modules 优先从 raw_data 取结构化字典，fallback 用字符串列表
        raw_modules = []
        if hint.raw_data:
            raw_modules = hint.raw_data.get("key_modules", [])

        if raw_modules or hint.key_modules:
            lines += ["## 关键模块拆解", ""]

            if raw_modules and isinstance(raw_modules[0], dict):
                # 结构化字典格式（来自 raw_data）
                for m in raw_modules:
                    name       = m.get("name",              "未命名模块")
                    func       = m.get("function",          "")
                    motivation = m.get("design_motivation", "")
                    io_desc    = m.get("input_output",      "")
                    code_hint  = m.get("code_hint",         "")

                    lines += [f"### {name}", ""]
                    if func:
                        lines += [f"**功能**：{func}", ""]
                    if motivation:
                        lines += [f"**设计动机**：{motivation}", ""]
                    if io_desc:
                        lines += [f"**输入/输出**：{io_desc}", ""]
                    if code_hint:
                        lines += [f"**代码位置提示**：`{code_hint}`", ""]
            else:
                # 已压缩为字符串的格式（hint.key_modules）
                for m in hint.key_modules:
                    lines.append(f"- {m}")
                lines.append("")

        # data_flow：hint.data_flow 已是字符串
        if hint.data_flow:
            lines += [
                "## 数据流分析",
                "",
                str(hint.data_flow),
                "",
            ]

        # file_hints：hint.file_hints 已是字符串列表
        if hint.file_hints:
            lines += ["## 推测代码文件结构", ""]
            for fh in hint.file_hints:
                lines.append(f"- {fh}")
            lines.append("")

        if hint.notes:
            lines += [
                "## 补充说明",
                "",
                str(hint.notes),
                "",
            ]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # ── TASK1：Figure 溯源 MD ─────────────────────────────────────────

    def _write_trace_md(self, trace, path: Path) -> None:
        """输出 Figure 溯源 Markdown 报告"""
        lines = [
            "# Figure 自动溯源报告",
            "",
            f"**架构图摘要**：{trace.arch_hint_summary[:200]}",
            f"**溯源置信度**：{trace.confidence}",
            f"**搜索查询**：{' / '.join(trace.search_queries[:3])}",
            "",
            "---",
            "",
        ]

        if trace.best_match:
            bm = trace.best_match
            lines += [
                "## ✅ 最可能的原论文",
                "",
                f"**标题**：{bm.title}",
                f"**年份 / 期刊**：{bm.year or '未知'} / {bm.venue or '未知'}",
                f"**作者**：{', '.join(bm.authors[:4])}{'...' if len(bm.authors) > 4 else ''}",
                f"**被引用数**：{bm.citation_count} 次",
                "",
                "**论文链接**：",
            ]
            if bm.pdf_url:
                lines.append(f"- 📄 [开放获取 PDF]({bm.pdf_url})")
            if bm.arxiv_id:
                lines.append(
                    f"- 📑 [arXiv:{bm.arxiv_id}](https://arxiv.org/abs/{bm.arxiv_id})"
                )
            lines.append(f"- 🔗 [Semantic Scholar]({bm.s2_url})")
            if bm.code_url:
                lines.append(f"- 💻 [代码仓库]({bm.code_url})")
            lines += [
                "",
                f"**摘要节选**：{bm.abstract[:300]}{'...' if len(bm.abstract) > 300 else ''}",
                "",
            ]

        if trace.trace_summary:
            lines += ["## 溯源结论", "", trace.trace_summary, ""]

        if len(trace.candidates) > 1:
            lines += [
                "## 其他候选论文",
                "",
                "| # | 标题 | 年份 | 期刊 | 引用数 | 链接 |",
                "|:--:|:--|:--:|:--|:--:|:--|",
            ]
            for i, c in enumerate(trace.candidates[1:6], 2):
                pdf_link   = f"[PDF]({c.pdf_url})" if c.pdf_url else "-"
                arxiv_link = (
                    f"[arXiv](https://arxiv.org/abs/{c.arxiv_id})"
                    if c.arxiv_id else "-"
                )
                links = " / ".join(x for x in [pdf_link, arxiv_link] if x != "-") or "-"
                lines.append(
                    f"| {i} | {c.title} | {c.year or '-'} | "
                    f"{(c.venue[:25] if c.venue else '-')} | "
                    f"{c.citation_count} | {links} |"
                )
            lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # ── TASK2：架构-代码双向验证 MD ──────────────────────────────────

    def _write_validation_md(self, val, path: Path) -> None:
        """输出架构-代码双向验证 Markdown 报告"""
        lines = [
            "# 架构图 ↔ 代码 双向验证报告",
            "",
            "## 验证摘要",
            "",
            "| 项目 | 数值 |",
            "|:---|:---:|",
            f"| 架构图声称模块数 | {val.total_arch_modules} |",
            f"| ✅ 已在代码中验证 | {val.verified_count} |",
            f"| 🔶 部分匹配（需人工确认） | {val.partial_count} |",
            f"| ❌ 代码中未找到 | {val.missing_count} |",
            f"| 🔍 代码有但图未画 | {val.code_only_count} |",
            f"| **架构一致性得分** | **{val.consistency_score}%** |",
            "",
            f"**结论**：{val.conclusion}",
            "",
            "---",
            "",
            "## 逐模块验证详情",
            "",
        ]

        status_order = {"verified": 0, "partial": 1, "missing": 2}
        sorted_matches = sorted(
            val.arch_to_code_matches,
            key=lambda m: status_order.get(m.status, 3)
        )

        for m in sorted_matches:
            icon = {"verified": "✅", "partial": "🔶", "missing": "❌"}.get(m.status, "❓")
            lines += [
                f"### {icon} {m.arch_module_name}",
                "",
                f"**架构图描述**：{m.arch_description or '（无详细描述）'}",
                f"**匹配状态**：{m.status}（匹配度 {m.match_score:.0f}%，方法：{m.match_method or '-'}）",
            ]
            if m.code_name:
                lines.append(f"**对应代码**：`{m.code_name}`")
            if m.code_location:
                lines.append(f"**代码位置**：`{m.code_location}`")
            lines += [f"**验证说明**：{m.verification_note}", ""]

        if val.code_only_modules:
            lines += [
                "## 🔍 代码中存在但架构图未画出的模块",
                "",
                "| 模块名 | 代码位置 | 类型 | 说明 |",
                "|:--|:--|:--|:--|",
            ]
            for m in val.code_only_modules:
                lines.append(
                    f"| `{m['name']}` | `{m['location']}` | "
                    f"{m['type']} | {m['note']} |"
                )
            lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
