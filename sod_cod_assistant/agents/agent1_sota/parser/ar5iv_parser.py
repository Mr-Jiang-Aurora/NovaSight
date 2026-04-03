"""
级别 A：ar5iv HTML 版本解析器
ar5iv 将 arXiv 论文的 LaTeX 源码编译为结构化 HTML，
表格标签完整保留，是最准确的提取来源。
覆盖约 75% 的 arXiv 论文（有 LaTeX 源码且编译成功的论文）。

支持两种常见 SOTA 对比表格结构：
  1. 数据集为行标签（Dataset | Sm | Em | MAE | …）
  2. 数据集为列头，方法为行（Method | COD10K Sm | CAMO Sm | …）
"""

from __future__ import annotations

import re
import asyncio
import logging
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from agents.agent1_sota.parser.metric_extractor import VALID_METRICS

logger = logging.getLogger(__name__)


class Ar5ivParser:
    """ar5iv HTML 版本解析器（级别 A）"""

    BASE_URL = "https://ar5iv.labs.arxiv.org/html"

    async def parse(
        self,
        arxiv_id: str,
        domain_keywords: list[str],
        dataset_names: list[str],
    ) -> Optional[list[dict]]:
        """
        下载 ar5iv HTML 版本，提取 SOTA 对比表格。

        Returns:
            表格数据列表，每个元素为
            {"dataset": str, "metrics": {"Sm": 0.xxx, ...}}
            或 None（无法获取/解析）
        """
        html = await self._fetch_html(arxiv_id)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")
        tables = soup.find_all("table")
        if not tables:
            return None

        results = []
        for table in tables:
            extracted = self._extract_table(table, dataset_names)
            if extracted:
                results.extend(extracted)

        return results if results else None

    async def _fetch_html(self, arxiv_id: str) -> Optional[str]:
        """下载 ar5iv HTML 页面"""
        clean_id = re.sub(r'v\d+$', '', arxiv_id.strip())
        url = f"{self.BASE_URL}/{clean_id}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=20),
                    headers={"User-Agent": "SOD-COD-Research-Assistant/1.0"},
                ) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"ar5iv 获取失败 {arxiv_id}: {e}")
            return None

    def _extract_table(
        self, table_tag, dataset_names: list[str]
    ) -> Optional[list[dict]]:
        """
        尝试两种表格结构提取：
        1. 数据集为行标签（原有策略）
        2. 数据集为列头，方法为行（新增策略）
        """
        from config.knowledge_base import normalize_metric_name

        all_text = table_tag.get_text().lower()

        # 快速过滤：表格内必须包含数据集名或指标关键词
        has_dataset = any(ds.lower() in all_text for ds in dataset_names)
        has_metric  = any(
            kw in all_text
            for kw in ["sm", "em", "mae", "fm", "measure", "error"]
        )
        if not (has_dataset or has_metric):
            return None

        # 策略 1：数据集名出现在行的第一列
        result = self._strategy_dataset_as_row(
            table_tag, dataset_names, normalize_metric_name
        )
        if result:
            return result

        # 策略 2：数据集名出现在列头（多行表头 / 复合列名）
        result = self._strategy_dataset_as_col_header(
            table_tag, dataset_names, normalize_metric_name
        )
        return result

    # ── 策略 1：数据集为行标签 ───────────────────────────────────────
    def _strategy_dataset_as_row(
        self, table_tag, dataset_names, normalize_fn
    ) -> Optional[list[dict]]:
        """原有策略：每行第一列为数据集名。"""
        header_row = table_tag.find("tr")
        if not header_row:
            return None

        headers = [cell.get_text(strip=True)
                   for cell in header_row.find_all(["th", "td"])]
        if not headers:
            return None

        rows    = table_tag.find_all("tr")[1:]
        results = []
        current_dataset = None

        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if not cells:
                continue

            for ds in dataset_names:
                if ds.lower() in cells[0].lower():
                    current_dataset = ds
                    break

            if not current_dataset:
                continue

            metrics: dict[str, float] = {}
            for i, header in enumerate(headers[1:], 1):
                if i >= len(cells):
                    break
                std_metric = normalize_fn(header)
                value_str  = cells[i].replace(",", "").strip()

                if std_metric not in VALID_METRICS:
                    if header.strip():
                        logger.debug(
                            f"[ar5iv-S1] 未识别列名：'{header}' → '{std_metric}'"
                        )
                    continue

                try:
                    value = float(value_str)
                    if value > 1.0:
                        value = value / 100.0
                    metrics[std_metric] = round(value, 4)
                except ValueError:
                    continue

            if metrics:
                results.append({"dataset": current_dataset, "metrics": metrics})

        return results if results else None

    # ── 策略 2：数据集为列头 ─────────────────────────────────────────
    def _strategy_dataset_as_col_header(
        self, table_tag, dataset_names, normalize_fn
    ) -> Optional[list[dict]]:
        """
        新策略：数据集名出现在列头（含 colspan 多行表头）。

        典型结构：
            Method | COD10K (colspan=4) | CAMO (colspan=4)
                   | Sm  Em  MAE  Fm   | Sm  Em  MAE  Fm
            SINet  | .772 .806 .051 .742 | .745 .804 .092 .695
            Ours   | .862 .912 .031 .832 | .800 .865 .055 .763

        或更简单的单行列头：
            Method | COD10K_Sm | COD10K_Em | CAMO_Sm | CAMO_Em
        """
        all_rows = table_tag.find_all("tr")
        if len(all_rows) < 2:
            return None

        # ── 分离表头行与数据行 ──────────────────────────────────────
        header_rows = []
        data_rows   = []
        for row in all_rows:
            if row.find("th"):
                header_rows.append(row)
            else:
                data_rows.append(row)

        # 若无 <th> 标签，用前两行作为表头
        if not header_rows:
            header_rows = all_rows[:2]
            data_rows   = list(all_rows[2:])
        if not data_rows:
            data_rows = all_rows[len(header_rows):]

        # ── 构建列映射：col_idx → (dataset, metric) ─────────────────
        # 第一遍：从表头行收集数据集和指标信息（处理 colspan）
        col_dataset: dict[int, str] = {}
        col_metric:  dict[int, str] = {}

        for row in header_rows:
            col = 0
            for cell in row.find_all(["th", "td"]):
                colspan = int(cell.get("colspan", 1))
                text    = cell.get_text(strip=True)

                # 检查数据集名
                for ds in dataset_names:
                    if ds.lower() in text.lower():
                        for c in range(col, col + colspan):
                            if c not in col_dataset:
                                col_dataset[c] = ds
                        break

                # 检查指标名
                std = normalize_fn(text)
                if std in VALID_METRICS:
                    for c in range(col, col + colspan):
                        if c not in col_metric:
                            col_metric[c] = std

                # 尝试同一单元格同时包含数据集+指标（如 "COD10K Sm"）
                text_l = text.lower()
                for ds in dataset_names:
                    if ds.lower() in text_l:
                        remaining = text_l.replace(ds.lower(), "").strip(" _()")
                        std2 = normalize_fn(remaining)
                        if std2 in VALID_METRICS:
                            for c in range(col, col + colspan):
                                if c not in col_dataset:
                                    col_dataset[c] = ds
                                if c not in col_metric:
                                    col_metric[c] = std2
                        break

                col += colspan

        # 第二遍：若某列只有数据集没有指标，尝试从第一条数据行读取子指标
        first_data_cells = []
        if data_rows:
            first_data_cells = [
                c.get_text(strip=True)
                for c in data_rows[0].find_all(["td", "th"])
            ]

        # 检查第一数据行是否实为指标子表头
        n_metric_in_first = sum(
            1 for cell in first_data_cells
            if normalize_fn(cell) in VALID_METRICS
        )
        first_row_is_subheader = n_metric_in_first >= 2

        if first_row_is_subheader:
            for i, cell_text in enumerate(first_data_cells):
                std = normalize_fn(cell_text)
                if std in VALID_METRICS and i not in col_metric:
                    col_metric[i] = std
            data_rows = data_rows[1:]  # 跳过子表头行

        # 第三遍：从左向右传播数据集名（处理 colspan 展开后的空列）
        current_ds = None
        max_col = max(
            list(col_dataset.keys()) + list(col_metric.keys()) + [0]
        ) + 1
        for c in range(max_col):
            if c in col_dataset:
                current_ds = col_dataset[c]
            elif current_ds and c in col_metric:
                col_dataset[c] = current_ds

        # 最终列映射
        col_map: dict[int, tuple[str, str]] = {}
        for c in range(max_col):
            ds     = col_dataset.get(c)
            metric = col_metric.get(c)
            if ds and metric:
                col_map[c] = (ds, metric)

        if not col_map:
            logger.debug("[ar5iv-S2] 未能建立列映射，跳过")
            return None

        logger.debug(f"[ar5iv-S2] 列映射：{col_map}")

        # ── 找"最优行"：优先含 "ours" 的行，否则取有效数值最多的行 ──
        best_row      = None
        best_count    = 0
        ours_row      = None

        for row in data_rows:
            row_cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if not row_cells:
                continue

            # "Ours" 行优先
            if any("our" in t.lower() for t in row_cells[:2]):
                ours_row = row_cells
                break

            # 统计在已知列位置能解析出的浮点数个数
            valid_count = 0
            for col_idx in col_map:
                if col_idx < len(row_cells):
                    try:
                        float(row_cells[col_idx].replace(",", ""))
                        valid_count += 1
                    except ValueError:
                        pass
            if valid_count > best_count:
                best_count = valid_count
                best_row   = row_cells

        cells = ours_row if ours_row else best_row
        if not cells:
            return None

        results_by_ds: dict[str, dict] = {}
        for col_idx, (ds, metric) in col_map.items():
            if col_idx >= len(cells):
                continue
            val_str = cells[col_idx].replace(",", "").strip()
            try:
                val = float(val_str)
                if val > 1.0:
                    val = val / 100.0
                if ds not in results_by_ds:
                    results_by_ds[ds] = {"dataset": ds, "metrics": {}}
                results_by_ds[ds]["metrics"][metric] = round(val, 4)
            except ValueError:
                continue

        results = [v for v in results_by_ds.values() if v["metrics"]]
        if results:
            logger.debug(f"[ar5iv-S2] 成功提取 {len(results)} 个数据集")
        return results if results else None
