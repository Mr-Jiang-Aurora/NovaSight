"""
级别 B：PyMuPDF 规则提取器
使用 PyMuPDF 的 find_tables() 方法提取标准边框表格。
适用于有明确边框线的表格（toprule/bottomrule 等）。

支持两种常见 SOTA 对比表格结构：
  1. 数据集为行标签（Dataset | Sm | Em | MAE | …）
  2. 数据集为列头，方法为行（Method | COD10K Sm | CAMO Sm | …）
"""

from __future__ import annotations

import logging
from typing import Optional

import fitz  # PyMuPDF

from agents.agent1_sota.parser.metric_extractor import VALID_METRICS

logger = logging.getLogger(__name__)


class PyMuPDFParser:
    """PyMuPDF 规则提取器（级别 B）"""

    def parse(
        self,
        pdf_path: str,
        candidate_pages: list[int],
        dataset_names: list[str],
    ) -> Optional[list[dict]]:
        """
        在候选页上使用 PyMuPDF find_tables() 提取表格。
        """
        from config.knowledge_base import normalize_metric_name

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            logger.error(f"无法打开 PDF: {pdf_path} -> {e}")
            return None

        all_results = []

        for page_num in candidate_pages:
            if page_num >= len(doc):
                continue

            page = doc[page_num]

            try:
                tabs = page.find_tables()
                if not tabs.tables:
                    continue

                for tab in tabs.tables:
                    df = tab.to_pandas()
                    if df.empty:
                        continue

                    extracted = self._process_dataframe(
                        df, dataset_names, normalize_metric_name
                    )
                    if extracted:
                        all_results.extend(extracted)

            except Exception as e:
                logger.debug(f"PyMuPDF 表格提取异常（页 {page_num}）: {e}")
                continue

        doc.close()
        return all_results if all_results else None

    def _process_dataframe(
        self, df, dataset_names: list[str], normalize_fn
    ) -> list[dict]:
        """尝试两种表格结构提取。"""
        if df.shape[0] < 2 or df.shape[1] < 2:
            return []

        # 策略 1：数据集名出现在行的第一列
        result = self._strategy_dataset_as_row(df, dataset_names, normalize_fn)
        if result:
            return result

        # 策略 2：数据集名出现在列头
        return self._strategy_dataset_as_col_header(df, dataset_names, normalize_fn)

    # ── 策略 1：数据集为行标签（原有逻辑）──────────────────────────
    def _strategy_dataset_as_row(
        self, df, dataset_names: list[str], normalize_fn
    ) -> list[dict]:
        headers = [str(c).strip() for c in df.columns.tolist()]

        has_relevant = any(
            ds.lower() in df.to_string().lower() for ds in dataset_names
        )
        if not has_relevant:
            return []

        results = []
        current_dataset = None

        for _, row in df.iterrows():
            cells = [str(c).strip() for c in row.tolist()]
            if not cells:
                continue

            for ds in dataset_names:
                if ds.lower() in cells[0].lower():
                    current_dataset = ds
                    break

            if not current_dataset:
                continue

            metrics: dict[str, float] = {}
            for i, header in enumerate(headers):
                if i >= len(cells):
                    break
                std_metric = normalize_fn(header)
                if std_metric in VALID_METRICS:
                    try:
                        val = float(cells[i].replace(",", ""))
                        if val > 1.0:
                            val = val / 100.0
                        metrics[std_metric] = round(val, 4)
                    except (ValueError, TypeError):
                        continue
                elif header.strip():
                    logger.debug(
                        f"[PyMuPDF-S1] 未识别列名：'{header}' → '{std_metric}'"
                    )

            if metrics:
                results.append({"dataset": current_dataset, "metrics": metrics})

        return results

    # ── 策略 2：数据集为列头 ─────────────────────────────────────────
    def _strategy_dataset_as_col_header(
        self, df, dataset_names: list[str], normalize_fn
    ) -> list[dict]:
        """
        处理列名中包含数据集信息的表格，支持两种子格式：
        a. 列名同时含数据集+指标（如 "COD10K Sm"）
        b. 双行表头：第一列头行含数据集，第一数据行含指标子表头
        """
        headers = [str(c).strip() for c in df.columns.tolist()]

        col_dataset: dict[int, str] = {}
        col_metric:  dict[int, str] = {}

        # ── a. 列名直接含 "DatasetName MetricName" ──────────────────
        for i, h in enumerate(headers):
            h_lower = h.lower()
            for ds in dataset_names:
                if ds.lower() in h_lower:
                    col_dataset[i] = ds
                    remaining = h_lower.replace(ds.lower(), "").strip(" _()")
                    std = normalize_fn(remaining)
                    if std in VALID_METRICS:
                        col_metric[i] = std
                    break
            # 也单独尝试指标名（用于后续继承逻辑）
            if i not in col_metric:
                std = normalize_fn(h)
                if std in VALID_METRICS:
                    col_metric[i] = std

        # ── b. 检查第一数据行是否为指标子表头 ───────────────────────
        first_row_cells = [str(c).strip() for c in df.iloc[0].tolist()]
        n_metric = sum(
            1 for cell in first_row_cells if normalize_fn(cell) in VALID_METRICS
        )
        first_row_is_subheader = n_metric >= 2

        if first_row_is_subheader:
            for i, cell in enumerate(first_row_cells):
                std = normalize_fn(cell)
                if std in VALID_METRICS and i not in col_metric:
                    col_metric[i] = std
            data_df = df.iloc[1:]
        else:
            data_df = df

        # ── 从左向右传播数据集名 ─────────────────────────────────────
        current_ds = None
        max_col = max(
            list(col_dataset.keys()) + list(col_metric.keys()) + [0]
        ) + 1
        for c in range(max_col):
            if c in col_dataset:
                current_ds = col_dataset[c]
            elif current_ds and c in col_metric:
                col_dataset[c] = current_ds

        # ── 最终列映射 ───────────────────────────────────────────────
        col_map: dict[int, tuple[str, str]] = {}
        for c in range(max_col):
            ds     = col_dataset.get(c)
            metric = col_metric.get(c)
            if ds and metric:
                col_map[c] = (ds, metric)

        if not col_map:
            return []

        logger.debug(f"[PyMuPDF-S2] 列映射：{col_map}")

        if data_df.empty:
            return []

        # ── 找"最优行"：优先含 "ours" 的行，否则取有效数值最多的行 ──
        best_cells = None
        best_count = 0
        ours_cells = None

        for _, row in data_df.iterrows():
            cells = [str(c).strip() for c in row.tolist()]
            if not cells:
                continue

            if "our" in cells[0].lower():
                ours_cells = cells
                break

            valid_count = 0
            for col_idx in col_map:
                if col_idx < len(cells):
                    try:
                        float(cells[col_idx].replace(",", ""))
                        valid_count += 1
                    except (ValueError, TypeError):
                        pass
            if valid_count > best_count:
                best_count = valid_count
                best_cells = cells

        cells = ours_cells if ours_cells else best_cells
        if not cells:
            return []
        results_by_ds: dict[str, dict] = {}

        for col_idx, (ds, metric) in col_map.items():
            if col_idx >= len(cells):
                continue
            try:
                val = float(cells[col_idx].replace(",", ""))
                if val > 1.0:
                    val = val / 100.0
                if ds not in results_by_ds:
                    results_by_ds[ds] = {"dataset": ds, "metrics": {}}
                results_by_ds[ds]["metrics"][metric] = round(val, 4)
            except (ValueError, TypeError):
                continue

        results = [v for v in results_by_ds.values() if v["metrics"]]
        if results:
            logger.debug(f"[PyMuPDF-S2] 成功提取 {len(results)} 个数据集")
        return results
