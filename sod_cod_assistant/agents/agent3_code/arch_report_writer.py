"""Agent3 报告输出器"""

import json
import logging
from datetime import datetime
from pathlib import Path
from shared.models import Agent3Report

logger = logging.getLogger(__name__)


class ArchReportWriter:
    """Agent3 报告输出器"""

    def write_all(self, report: Agent3Report, output_dir: str) -> dict[str, str]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        paths = {}

        json_path = out / f"agent3_report_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(mode="json"),
                      f, ensure_ascii=False, indent=2, default=str)
        paths["json"] = str(json_path)

        md_path = out / f"agent3_report_{ts}.md"
        self._write_md(report, md_path)
        paths["markdown"] = str(md_path)

        summary_path = out / f"agent3_summary_{ts}.txt"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(report.summary or report.narrative[:500])
        paths["summary"] = str(summary_path)

        logger.info(f"Agent3 报告已保存：{paths}")
        return paths

    def _write_md(self, report: Agent3Report, path: Path) -> None:
        a = report.analysis
        lines = [
            "# 用户代码架构分析报告",
            f"**生成时间**：{report.generated_at.strftime('%Y-%m-%d %H:%M')}  ",
            f"**输入模式**：{a.input_mode if a else '-'}  ",
            "",
        ]

        if not a or a.status == "failed":
            lines += [f"**分析失败**：{a.fail_reason if a else '未知原因'}"]
        else:
            lines += [
                "## 架构摘要",
                "",
                a.arch_summary or "（未生成）",
                "",
                f"**框架**：{a.framework or '-'}  ",
            ]
            if a.train_config:
                tc = a.train_config
                lines.append(
                    f"**训练配置**：bs={tc.batch_size} | "
                    f"lr={tc.learning_rate} | "
                    f"epochs={tc.epochs} | "
                    f"optimizer={tc.optimizer} | "
                    f"input={tc.input_size}"
                )
            lines.append("")

            if a.components:
                lines += ["## 识别到的架构组件", ""]
                for c in a.components:
                    pretrain = f"（预训练于 {c.pretrained_on}）" if c.is_pretrained else ""
                    line_info = f" [第{c.line_number}行]" if c.line_number else ""
                    lines.append(
                        f"- **{c.component_type}**：{c.name}{pretrain}  "
                        f"→ `{c.source_file}`{line_info}"
                    )
                lines.append("")

            if a.losses:
                lines += ["## 损失函数", ""]
                for loss_item in a.losses:
                    aux = "（辅助损失）" if loss_item.is_auxiliary else ""
                    lines.append(f"- {loss_item.loss_name}  weight={loss_item.weight}{aux}")
                lines.append("")

            if a.potential_issues:
                lines += ["## ⚠️ 潜在问题", ""]
                for issue in a.potential_issues:
                    lines.append(f"- {issue}")
                lines.append("")

            if a.suggestions:
                lines += ["## 💡 改进建议", ""]
                priority_order = {"high": 0, "medium": 1, "low": 2}
                sorted_suggestions = sorted(
                    a.suggestions,
                    key=lambda s: priority_order.get(s.priority, 1)
                )
                for i, s in enumerate(sorted_suggestions, 1):
                    icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.priority, "⚪")
                    lines += [
                        f"### {i}. {icon} [{s.category.upper()}] {s.priority.upper()} 优先",
                        f"{s.suggestion}",
                    ]
                    if s.reference:
                        lines.append(f"**参考**：{s.reference}")
                    if s.code_hint:
                        lines.append(f"**代码提示**：`{s.code_hint}`")
                    lines.append("")

            # SOTA 差距与改进路线图
            if a.sota_gap_summary:
                lines += ["## SOTA 差距分析与改进路线图", ""]
                for line in a.sota_gap_summary.splitlines():
                    lines.append(line)
                lines.append("")

            # 逐文件分析（来自 key_innovations 中以 [ 开头的条目）
            file_entries  = [x for x in a.key_innovations if x.startswith("[")]
            other_entries = [x for x in a.key_innovations if not x.startswith("[")]

            if file_entries:
                lines += ["## 逐文件分析", ""]
                for entry in file_entries:
                    lines.append(f"- {entry}")
                lines.append("")

            if other_entries:
                lines += ["## 核心创新点", ""]
                for inn in other_entries:
                    lines.append(f"- {inn}")
                lines.append("")

        if report.narrative:
            lines += ["---", "", "## 完整诊断报告（AI 生成）", "", report.narrative]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
