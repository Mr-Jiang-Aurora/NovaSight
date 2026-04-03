"""
输出层：排行榜 + 失败报告生成器
Phase 3 完成后，输出三个文件：
  1. sota_ranking_{domain}_{timestamp}.json    完整排行榜数据
  2. sota_ranking_{domain}_{timestamp}.md      可读 Markdown 排行榜
  3. failed_extraction_{domain}_{timestamp}.md 解析失败论文列表
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from shared.models import PaperRecord, ParseReport, SOTALeaderboard

logger = logging.getLogger(__name__)


class ReportGenerator:
    """排行榜与失败报告生成器"""

    def generate_all(
        self,
        leaderboard: SOTALeaderboard,
        parse_report: ParseReport,
        output_dir: str,
    ) -> dict[str, str]:
        """
        生成所有输出文件。

        Returns:
            {"ranking_json": path, "ranking_md": path, "failure_md": path}
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
        domain = leaderboard.domain

        paths: dict[str, str] = {}

        # 文件1：排行榜 JSON
        json_path = output_path / f"sota_ranking_{domain}_{ts}.json"
        self._write_ranking_json(leaderboard, json_path)
        paths["ranking_json"] = str(json_path)
        logger.info(f"排行榜 JSON 已保存：{json_path}")

        # 文件2：排行榜 Markdown
        md_path = output_path / f"sota_ranking_{domain}_{ts}.md"
        self._write_ranking_md(leaderboard, md_path)
        paths["ranking_md"] = str(md_path)
        logger.info(f"排行榜 Markdown 已保存：{md_path}")

        # 文件3：失败报告 Markdown（只在有失败记录时生成）
        if parse_report.failures:
            fail_path = output_path / f"failed_extraction_{domain}_{ts}.md"
            parse_report.export_markdown(str(fail_path))
            paths["failure_md"] = str(fail_path)
            logger.info(
                f"失败报告已保存：{fail_path} "
                f"（{parse_report.failure_count} 篇需手动查阅）"
            )
        else:
            logger.info("所有论文解析成功，无失败报告")

        return paths

    def _write_ranking_json(
        self, leaderboard: SOTALeaderboard, path: Path
    ) -> None:
        """写入完整的排行榜 JSON"""
        data = leaderboard.model_dump(mode="json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def _write_ranking_md(
        self, leaderboard: SOTALeaderboard, path: Path
    ) -> None:
        """
        写入 Markdown 格式的 SOTA 排行榜。

        排行榜结构：
        - 按主数据集（如 COD10K）的主指标（如 Sm）降序排列
        - 每个数据集单独一个表格
        - 含论文链接、代码链接、CCF 等级
        """
        from config.knowledge_base import DOMAIN_KNOWLEDGE_BASE

        domain_info    = DOMAIN_KNOWLEDGE_BASE.get(leaderboard.domain, {})
        datasets       = domain_info.get("datasets", [])
        primary_metric = domain_info.get("primary_metric", "Sm")
        primary_ds     = domain_info.get(
            "primary_dataset", datasets[0] if datasets else ""
        )

        lines = [
            f"# {leaderboard.domain} SOTA 排行榜",
            f"**生成时间**：{leaderboard.generated_at.strftime('%Y-%m-%d %H:%M')}",
            f"**论文总数**：{leaderboard.total_papers} 篇 | "
            f"**成功提取分数**："
            f"{sum(1 for p in leaderboard.papers if p.scores)} 篇",
            "",
        ]

        # 有分数的论文按主数据集主指标排序
        scored_papers = [
            p for p in leaderboard.papers
            if p.scores and primary_ds in p.scores
        ]
        scored_papers.sort(
            key=lambda p: (
                getattr(p.scores.get(primary_ds), primary_metric, 0) or 0
            ),
            reverse=True,
        )

        for dataset in datasets:
            ds_papers = [p for p in scored_papers if dataset in p.scores]
            if not ds_papers:
                continue

            lines += [
                f"## {dataset} 数据集",
                "",
                "| 排名 | 论文标题 | 发表来源 | CCF | 年份 "
                "| Sm↑ | Em↑ | MAE↓ | Fm↑ | 论文 | 代码 |",
                "|:---:|:--------|:--------|:---:|:---:"
                "|:---:|:---:|:---:|:---:|:---:|:---:|",
            ]

            # 按当前数据集的主指标降序排列
            ds_papers.sort(
                key=lambda p: (
                    getattr(p.scores.get(dataset), primary_metric, 0) or 0
                ),
                reverse=True,
            )

            for rank, paper in enumerate(ds_papers, 1):
                score = paper.scores[dataset]
                sm  = f"{score.Sm:.3f}"  if score.Sm  is not None else "-"
                em  = f"{score.Em:.3f}"  if score.Em  is not None else "-"
                mae = f"{score.MAE:.4f}" if score.MAE is not None else "-"
                fm  = f"{score.Fm:.3f}"  if score.Fm  is not None else "-"

                title_short = paper.title[:45] + (
                    "..." if len(paper.title) > 45 else ""
                )
                paper_link = (
                    f"[PDF]({paper.paper_url})" if paper.paper_url else "-"
                )
                code_link = (
                    f"[Code]({paper.code_url})" if paper.code_url else "-"
                )
                conf_str = (
                    f"**{paper.ccf_rank}**" if paper.ccf_rank else "-"
                )

                lines.append(
                    f"| {rank} | {title_short} | {paper.venue or '-'} | "
                    f"{conf_str} | {paper.year or '-'} | "
                    f"{sm} | {em} | {mae} | {fm} | "
                    f"{paper_link} | {code_link} |"
                )

            lines.append("")

        # 未提取到分数的论文列表
        unscored = [p for p in leaderboard.papers if not p.scores]
        if unscored:
            lines += [
                "## 未提取到分数的论文",
                "",
                "以下论文未能自动提取指标（PDF 获取失败或表格解析失败），"
                "请参阅失败报告手动补充：",
                "",
            ]
            for p in unscored:
                link = f"[链接]({p.paper_url})" if p.paper_url else "无链接"
                lines.append(
                    f"- [{p.venue or 'N/A'}] **{p.title}** "
                    f"({p.year or 'N/A'}) — {link}"
                )
            lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
