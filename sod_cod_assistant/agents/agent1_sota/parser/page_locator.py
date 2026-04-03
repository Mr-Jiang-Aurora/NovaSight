"""
阶段一：关键页定位器
使用 PyMuPDF 扫描 PDF 全文，找到包含 SOTA 对比表格的候选页码。
耗时极短（< 100ms），避免对全文所有页面进行昂贵的表格提取操作。
"""

from __future__ import annotations

import re
import logging
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PageLocator:
    """
    关键页定位器。
    通过关键词扫描快速锁定含 SOTA 对比表格的页码。
    """

    # 触发定位的关键词（任意一个出现即视为候选页）
    TABLE_KEYWORDS = [
        "table", "comparison", "benchmark",
        "state-of-the-art", "competing", "quantitative",
        "x", "up", "down",  # 指标方向符号（ASCII 替代）
    ]

    def locate_candidate_pages(
        self,
        pdf_path: str,
        domain_keywords: list[str],
        max_candidates: int = 8,        # 从 5 增加到 8
    ) -> list[int]:
        """
        扫描 PDF，返回包含 SOTA 对比表格的候选页码列表（0-indexed）。

        策略：
        1. 对所有页面打分（不再过滤 score==0）
        2. 优先返回高分页
        3. 如果全文没有任何关键词命中，启用 fallback：
           返回论文后 40% 的页码（实验结果表通常在论文后半部分）

        Args:
            pdf_path:         PDF 文件路径
            domain_keywords:  领域关键词（数据集名），如 ["COD10K","CAMO","NC4K"]
            max_candidates:   最多返回的候选页数

        Returns:
            候选页码列表（0-indexed），按「关键词命中数」降序排列
        """
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            logger.error(f"无法打开 PDF: {pdf_path} -> {e}")
            return []

        total_pages = len(doc)
        page_scores: dict[int, int] = {}

        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text().lower()

            score = 0

            # 领域数据集关键词命中（权重 3）
            for kw in domain_keywords:
                if kw.lower() in text:
                    score += 3

            # 表格通用关键词命中（权重 1）
            for kw in self.TABLE_KEYWORDS:
                if kw.lower() in text:
                    score += 1

            # 小数密度（四位小数如 0.8621 是指标的典型格式，权重高）
            four_decimal = len(re.findall(r'0\.\d{3,4}', text))
            score += min(four_decimal * 2, 20)

            # 表格符号（↑、↓ 大量出现意味着对比表格）
            symbol_count = text.count('\u2191') + text.count('\u2193') + text.count('\xd7')
            score += min(symbol_count, 10)

            page_scores[page_num] = score   # 所有页都记录，不过滤 0 分

        doc.close()

        # 按分数降序取前 N 页
        sorted_pages = sorted(
            page_scores.items(), key=lambda x: x[1], reverse=True
        )
        candidates = [p for p, _ in sorted_pages[:max_candidates]]

        # Fallback：如果所有候选页分数都为 0（完全没有关键词命中），
        # 取论文后 40% 的页码（实验章节通常在此区间）
        if all(page_scores.get(p, 0) == 0 for p in candidates):
            start = max(0, total_pages * 6 // 10)   # 从第 60% 页开始
            fallback = list(range(start, min(total_pages, start + 8)))
            logger.warning(
                f"关键词全未命中，启用 fallback 页码: {fallback}  ({pdf_path})"
            )
            return fallback

        logger.debug(f"候选页: {candidates}  ({pdf_path})")
        return candidates

    def detect_table_rotation(self, pdf_path: str, page_num: int) -> bool:
        """
        检测指定页面的表格是否旋转 90°。

        旋转表格的特征：
        1. 页面文字排列方向与正文不同
        2. PyMuPDF 的 block 坐标呈纵向分布而非横向
        3. 有大量文字高度 > 宽度的 block（正常文字宽 > 高）

        Returns:
            True 表示检测到旋转，False 表示正常
        """
        try:
            doc = fitz.open(pdf_path)
            page = doc[page_num]

            blocks = page.get_text("blocks")
            if not blocks:
                doc.close()
                return False

            # 统计高度 > 宽度的文字块比例
            rotated_count = 0
            total_count   = 0
            for block in blocks:
                x0, y0, x1, y1 = block[:4]
                width  = x1 - x0
                height = y1 - y0
                if width > 5 and height > 5:  # 过滤极小 block
                    total_count += 1
                    if height > width * 2:    # 高度超过宽度 2 倍 -> 可能旋转
                        rotated_count += 1

            doc.close()

            if total_count == 0:
                return False

            rotation_ratio = rotated_count / total_count
            is_rotated = rotation_ratio > 0.3  # 30% 以上 block 疑似旋转

            if is_rotated:
                logger.warning(
                    f"检测到旋转表格：页 {page_num}，"
                    f"旋转块比例 {rotation_ratio:.1%}"
                )
            return is_rotated

        except Exception as e:
            logger.debug(f"旋转检测失败：{e}")
            return False
