"""
论文信息卡片生成器
在 Agent1 完成搜索后，生成供用户浏览的论文信息 MD 文件。
包含：标题、期刊/会议、年份、CCF/中科院分区、影响因子、PDF 链接、代码链接、性能指标。
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class PaperCardWriter:
    """论文信息卡片生成器"""

    def write(
        self,
        papers: list,
        domain: str,
        output_dir: str,
    ) -> str:
        """
        生成论文信息卡片 MD 文件。

        Args:
            papers:     PaperRecord 列表（来自 Agent1）
            domain:     研究领域（COD/SOD）
            output_dir: 输出目录

        Returns:
            生成的 MD 文件路径
        """
        from config.venue_info import get_venue_info

        out  = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out / f"paper_cards_{domain}_{ts}.md"

        # 按综合得分排序（有分数的优先），无分数按年份降序
        scored   = sorted(
            [p for p in papers if p.scores],
            key=lambda p: self._composite_score(p),
            reverse=True,
        )
        unscored = sorted(
            [p for p in papers if not p.scores],
            key=lambda p: p.year or 0,
            reverse=True,
        )
        all_papers = scored + unscored

        lines = [
            f"# {domain} SOTA 论文信息卡片",
            f"",
            f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
            f"**论文总数**：{len(all_papers)} 篇（{len(scored)} 篇有指标数据）  ",
            f"**领域**：{domain}（Camouflaged/Salient Object Detection）",
            "",
            "> 📌 说明：付费期刊论文无法直接下载，请点击「期刊页面」链接通过学校图书馆（IEEE Xplore、Elsevier 等）访问。",
            "",
            "---",
            "",
        ]

        # 按 CCF 等级分组
        groups: dict = {
            "🏆 CCF-A 期刊/会议": [],
            "🥈 CCF-B 期刊/会议": [],
            "📊 SCI Q1（非CCF-A/B）": [],
            "📄 其他 / arXiv 预印本": [],
        }

        for paper in all_papers:
            vi  = get_venue_info(paper.venue or "")
            ccf = vi.get("ccf", "-")
            cas = vi.get("cas_tier", "-")
            if ccf == "A":
                groups["🏆 CCF-A 期刊/会议"].append((paper, vi))
            elif ccf == "B":
                groups["🥈 CCF-B 期刊/会议"].append((paper, vi))
            elif cas == "Q1":
                groups["📊 SCI Q1（非CCF-A/B）"].append((paper, vi))
            else:
                groups["📄 其他 / arXiv 预印本"].append((paper, vi))

        # 输出各分组统计
        lines += [
            "## 分区统计",
            "",
            "| 分区 | 篇数 |",
            "|:---|:---:|",
        ]
        for gname, gpapers in groups.items():
            if gpapers:
                lines.append(f"| {gname} | {len(gpapers)} |")
        lines += ["", "---", ""]

        # 逐组输出卡片
        for group_name, group_papers in groups.items():
            if not group_papers:
                continue
            lines += [f"## {group_name}（{len(group_papers)} 篇）", ""]
            for paper, vi in group_papers:
                lines.extend(self._render_card(paper, vi))

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"[PaperCards] 论文信息卡片已生成：{path}（{len(all_papers)} 篇）")
        return str(path)

    def _render_card(self, paper, venue_info: dict) -> List[str]:
        """渲染单篇论文的信息卡片"""
        ccf       = venue_info.get("ccf", "-")
        cas       = venue_info.get("cas_tier", "-")
        if_val    = venue_info.get("if_2023")
        full_name = venue_info.get("full_name") or paper.venue or "未知"

        # 分区标签
        tags = []
        if ccf != "-":
            tags.append(f"CCF-{ccf}")
        if cas != "-":
            tags.append(f"中科院{cas}")
        if if_val:
            tags.append(f"IF={if_val}")
        tag_str = " / ".join(tags) if tags else "未收录"

        lines = [
            f"### 📄 {paper.title or '（标题未知）'}",
            "",
            f"| 项目 | 内容 |",
            f"|:---|:---|",
            f"| 年份 | {paper.year or '未知'} |",
            f"| 期刊/会议 | {full_name} |",
            f"| 分区 | {tag_str} |",
        ]

        # 链接行
        links = []
        if paper.paper_url:
            is_paywalled = any(
                d in paper.paper_url
                for d in ["ieeexplore", "sciencedirect", "springer", "acm.org"]
            )
            if is_paywalled:
                if "ieeexplore" in paper.paper_url:
                    domain_hint = " — IEEE Xplore，校园网可免费访问"
                elif "sciencedirect" in paper.paper_url:
                    domain_hint = " — Elsevier，校园网可免费访问"
                elif "springer" in paper.paper_url:
                    domain_hint = " — Springer，校园网可免费访问"
                elif "acm.org" in paper.paper_url:
                    domain_hint = " — ACM DL，校园网可免费访问"
                else:
                    domain_hint = "，校园网可免费访问"
                links.append(f"[Journal page{domain_hint}]({paper.paper_url})")
            else:
                links.append(f"[📄 Open Access]({paper.paper_url})")

        arxiv_id = getattr(paper, "arxiv_id", None)
        if arxiv_id:
            links.append(f"[📑 arXiv:{arxiv_id}](https://arxiv.org/abs/{arxiv_id})")

        if paper.code_url:
            links.append(f"[Code]({paper.code_url})")
        else:
            links.append("No code — check [Papers With Code](https://paperswithcode.com)")

        lines.append(f"| 链接 | {' / '.join(links) if links else '-'} |")

        # 性能指标
        if paper.scores:
            lines.append(f"| 指标 | （见下方） |")

        lines.append("")

        if paper.scores:
            lines.append("**性能指标**：")
            for dataset, metrics in paper.scores.items():
                sm  = f"{metrics.Sm:.3f}"  if metrics.Sm  else "-"
                em  = f"{metrics.Em:.3f}"  if metrics.Em  else "-"
                fm  = f"{metrics.Fm:.3f}"  if metrics.Fm  else "-"
                mae = f"{metrics.MAE:.4f}" if metrics.MAE else "-"
                lines.append(
                    f"  - **{dataset}**：Sm={sm} | Em={em} | Fm={fm} | MAE={mae}"
                )
            lines.append("")

        # 摘要节选（空摘要给明确提示而非静默跳过）
        abstract = getattr(paper, "abstract", None) or ""
        if abstract.strip():
            abstract_short = abstract[:250] + "..." if len(abstract) > 250 else abstract
            lines += ["**摘要节选**：", f"> {abstract_short}", ""]
        else:
            lines += [
                "**摘要**：暂无（建议访问上方 Semantic Scholar 链接查看完整摘要）",
                "",
            ]

        # venue 未匹配时追加手动查询提示
        if not venue_info.get("_matched", True):
            lines.append(
                "> ℹ️ 分区信息未收录（该期刊/会议不在映射表中）。"
                "可在 [letpub.com](https://www.letpub.com.cn/index.php?page=journalapp)"
                " 或 [CCF 推荐列表](https://www.ccf.org.cn/Academic_Evaluation/By_category/)"
                " 中手动查询。\n"
            )

        lines += ["---", ""]
        return lines

    def _composite_score(self, paper) -> float:
        """计算综合得分（取各数据集 Sm 均值），用于排序"""
        if not paper.scores:
            return 0.0
        total, count = 0.0, 0
        for metrics in paper.scores.values():
            if metrics.Sm:
                total += metrics.Sm
                count += 1
        return total / max(count, 1)
