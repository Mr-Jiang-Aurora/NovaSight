"""
Agent2 报告输出器
将诊断结果写入 JSON + Markdown + 精简摘要三种格式。
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from shared.models import Agent2Report, DatasetRanking

logger = logging.getLogger(__name__)


class ReportWriter:
    """Agent2 报告输出器"""

    def write_all(
        self,
        report: Agent2Report,
        output_dir: str,
    ) -> dict[str, str]:
        """
        输出三个文件：JSON、Markdown、精简摘要。

        Returns:
            {"json": path, "markdown": path, "summary": path}
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
        domain = report.domain
        paths  = {}

        # 文件1：完整 JSON
        json_path = out / f"agent2_report_{domain}_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                report.model_dump(mode="json"),
                f, ensure_ascii=False, indent=2, default=str,
            )
        paths["json"] = str(json_path)
        logger.info(f"JSON 报告已保存：{json_path}")

        # 文件2：Markdown 报告
        md_path = out / f"agent2_report_{domain}_{ts}.md"
        self._write_markdown(report, md_path)
        paths["markdown"] = str(md_path)
        logger.info(f"Markdown 报告已保存：{md_path}")

        # 文件3：精简摘要（纯文本）
        summary_path = out / f"agent2_summary_{domain}_{ts}.txt"
        summary_text = report.summary or (report.narrative[:500] if report.narrative else "（暂无摘要）")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_text)
        paths["summary"] = str(summary_path)
        logger.info(f"精简摘要已保存：{summary_path}")

        return paths

    def _write_markdown(self, report: Agent2Report, path: Path) -> None:
        lines = [
            f"# {report.domain} SOTA 指标对比诊断报告",
            f"**生成时间**：{report.generated_at.strftime('%Y-%m-%d %H:%M')}  ",
            f"**覆盖方法**：{report.scored_methods} 篇（共 {report.total_methods} 篇）",
            "",
            "---",
            "",
        ]

        # 一、综合得分排名
        lines += ["## 一、综合得分排名", ""]
        sorted_profiles = sorted(
            report.profiles, key=lambda p: p.overall_score, reverse=True
        )
        lines += [
            "| 排名 | 方法 | 来源 | 年份 | 综合得分 | 最强项 | 最弱项 |",
            "|:---:|:---|:---|:---:|:---:|:---:|:---:|",
        ]
        for i, p in enumerate(sorted_profiles, 1):
            strongest = (
                f"{p.strongest_dataset}/{p.strongest_metric}"
                if p.strongest_dataset else "-"
            )
            weakest = (
                f"{p.weakest_dataset}/{p.weakest_metric}"
                if p.weakest_dataset else "-"
            )
            lines.append(
                f"| {i} | {p.title[:40]} | {p.venue or '-'} | "
                f"{p.year or '-'} | {p.overall_score:.4f} | "
                f"{strongest} | {weakest} |"
            )
        lines.append("")

        # 二、分数据集排行榜（只展示各数据集 Sm 排名）
        lines += ["## 二、分数据集排行榜", ""]
        primary_metric = "Sm"
        for ranking in report.rankings:
            if ranking.metric != primary_metric:
                continue
            lines += [
                f"### {ranking.dataset}（{primary_metric}↑ 排名）",
                "",
                "| 排名 | 方法 | 来源 | 年份 | Sm | Em | MAE | 论文 | 代码 |",
                "|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|",
            ]
            em_ranking  = next(
                (r for r in report.rankings
                 if r.dataset == ranking.dataset and r.metric == "Em"),
                None,
            )
            mae_ranking = next(
                (r for r in report.rankings
                 if r.dataset == ranking.dataset and r.metric == "MAE"),
                None,
            )
            em_map  = {e.paper_id: e.value for e in (em_ranking.entries  if em_ranking  else [])}
            mae_map = {e.paper_id: e.value for e in (mae_ranking.entries if mae_ranking else [])}

            for entry in ranking.entries[:10]:
                paper_link = f"[📄]({entry.paper_url})" if entry.paper_url else "-"
                code_link  = f"[💻]({entry.code_url})"  if entry.code_url  else "-"
                em_val  = em_map.get(entry.paper_id)
                mae_val = mae_map.get(entry.paper_id)
                em_str  = f"{em_val:.3f}"  if em_val  is not None else "-"
                mae_str = f"{mae_val:.4f}" if mae_val is not None else "-"
                lines.append(
                    f"| {entry.rank} | {entry.title[:38]} | "
                    f"{entry.venue or '-'} | {entry.year or '-'} | "
                    f"{entry.value:.3f} | {em_str} | {mae_str} | "
                    f"{paper_link} | {code_link} |"
                )
            lines.append("")

        # 三、指标饱和度分析
        lines += ["## 三、指标饱和度分析", ""]
        status_zh = {
            "saturating":        "⚠️ 趋于饱和（年均进步 <0.2%）",
            "active":            "✅ 正常进步（0.2%-0.8%/年）",
            "rapid":             "🚀 快速进步（>0.8%/年）",
            "insufficient_data": "❓ 数据不足",
        }
        for ga in report.gap_analyses:
            lines.append(f"### {ga.dataset}")
            lines += [
                "| 指标 | 饱和度状态 | 当前方法间差距 |",
                "|:---|:---|:---:|",
            ]
            for metric, status in ga.saturation.items():
                gap = ga.current_range.get(metric, 0)
                lines.append(
                    f"| {metric} | {status_zh.get(status, status)} | {gap:.4f} |"
                )
            lines.append("")

        # 四、自然语言洞察（如有）
        if report.narrative:
            lines += [
                "## 四、研究洞察（AI 生成）",
                "",
                report.narrative,
                "",
            ]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
