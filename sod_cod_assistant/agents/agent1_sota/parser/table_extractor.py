"""
Agent1 - 第三层：表格解析层主入口
调度四级分级提取，并生成失败报告。

四级顺序（命中即停）：
  A -> ar5iv HTML（最准确，覆盖约75%）
  B -> PyMuPDF 规则提取（简单表格）
  C -> Docling 深度识别（复杂表格）
  D -> VLM 兜底（极端情况）
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

from shared.models import (
    PaperRecord, ExtractionConfidence,
    FailureReason, ParseReport,
)

logger = logging.getLogger(__name__)


class TableExtractor:
    """表格解析层主入口（调度四级分级提取）"""

    def __init__(self, settings) -> None:
        from .page_locator     import PageLocator
        from .ar5iv_parser     import Ar5ivParser
        from .pymupdf_parser   import PyMuPDFParser
        from .docling_parser   import DoclingParser
        from .vlm_parser       import VLMParser
        from .metric_extractor import MetricExtractor

        self.settings         = settings
        self.page_locator     = PageLocator()
        self.ar5iv_parser     = Ar5ivParser()
        self.pymupdf_parser   = PyMuPDFParser()
        self.docling_parser   = DoclingParser()
        self.metric_extractor = MetricExtractor()

        # VLM 只在配置了 ANTHROPIC_API_KEY 且 ENABLE_VLM_FALLBACK=True 时启用
        api_key     = getattr(settings, "ANTHROPIC_API_KEY", "")
        enable_vlm  = getattr(settings, "ENABLE_VLM_FALLBACK", True)

        if api_key and enable_vlm:
            try:
                # 传入 settings 对象（支持 base_url / model 配置）
                self.vlm_parser = VLMParser(settings)
            except Exception as e:
                logger.warning(f"VLM 初始化失败，级别 D 将被跳过：{e}")
                self.vlm_parser = None
        else:
            self.vlm_parser = None
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY 未配置，VLM 级别 D 将被跳过")
            elif not enable_vlm:
                logger.info("ENABLE_VLM_FALLBACK=False，VLM 级别 D 已禁用")

    async def extract_one(
        self,
        paper: PaperRecord,
        domain: str,
        parse_report: ParseReport,
    ) -> bool:
        """
        对单篇论文执行四级分级提取。

        Args:
            paper:        目标论文
            domain:       研究领域（COD/SOD）
            parse_report: 失败报告对象（失败时写入）

        Returns:
            True 表示提取成功，False 表示失败（已写入 parse_report）
        """
        from config.knowledge_base import DOMAIN_KNOWLEDGE_BASE

        domain_info   = DOMAIN_KNOWLEDGE_BASE.get(domain, {})
        dataset_names = domain_info.get("datasets", [])
        page_keywords = domain_info.get("page_keywords", [])

        # ── 前置检查：无 PDF ──────────────────────────────────────────
        if not paper.pdf_url:
            parse_report.add_failure(
                paper, FailureReason.NO_PDF,
                "Phase 2 未获取到 PDF，无法进入解析",
            )
            return False

        pdf_path = self._get_local_pdf_path(paper)
        if not pdf_path or not Path(pdf_path).exists():
            # PDF 未下载到本地，需先下载
            pdf_path = await self._download_pdf(paper)
            if not pdf_path:
                parse_report.add_failure(
                    paper, FailureReason.NO_PDF,
                    f"PDF 下载失败：{paper.pdf_url}",
                )
                return False

        # ── 阶段一：关键页定位 ────────────────────────────────────────
        candidate_pages = self.page_locator.locate_candidate_pages(
            pdf_path, page_keywords + dataset_names
        )
        if not candidate_pages:
            parse_report.add_failure(
                paper, FailureReason.NO_TABLE_FOUND,
                "关键词扫描未找到候选页面，可能表格在特殊位置",
                methods=["page_locator"],
            )
            return False

        # ── 旋转检测 ──────────────────────────────────────────────────
        is_rotated = any(
            self.page_locator.detect_table_rotation(pdf_path, p)
            for p in candidate_pages[:2]
        )

        attempted_methods: list[str] = []

        # ── 级别 A：ar5iv HTML ────────────────────────────────────────
        if paper.arxiv_id:
            attempted_methods.append("ar5iv")
            tables = await self.ar5iv_parser.parse(
                paper.arxiv_id, page_keywords, dataset_names
            )
            if tables:
                success = self.metric_extractor.write_scores(
                    paper, tables, domain, ExtractionConfidence.HIGH
                )
                if success:
                    logger.info(f"[A] ar5iv 成功：{paper.title[:40]}")
                    return True

        # ── 级别 B：PyMuPDF ───────────────────────────────────────────
        if not is_rotated:   # 旋转表格跳过 B 级，直接到 C/D
            attempted_methods.append("pymupdf")
            tables = self.pymupdf_parser.parse(
                pdf_path, candidate_pages, dataset_names
            )
            if tables:
                success = self.metric_extractor.write_scores(
                    paper, tables, domain, ExtractionConfidence.HIGH
                )
                if success:
                    logger.info(f"[B] PyMuPDF 成功：{paper.title[:40]}")
                    return True

        # ── 级别 C：Docling ───────────────────────────────────────────
        attempted_methods.append("docling")
        tables = self.docling_parser.parse(
            pdf_path, candidate_pages, dataset_names
        )
        if tables:
            success = self.metric_extractor.write_scores(
                paper, tables, domain, ExtractionConfidence.MEDIUM
            )
            if success:
                logger.info(f"[C] Docling 成功：{paper.title[:40]}")
                return True

        # ── 级别 D：VLM 兜底 ─────────────────────────────────────────
        if self.vlm_parser:
            attempted_methods.append("vlm")
            tables = self.vlm_parser.parse(
                pdf_path, candidate_pages, dataset_names, is_rotated
            )
            if tables:
                success = self.metric_extractor.write_scores(
                    paper, tables, domain, ExtractionConfidence.LOW
                )
                if success:
                    logger.info(f"[D] VLM 成功：{paper.title[:40]}")
                    return True

        # ── 所有级别均失败 ────────────────────────────────────────────
        reason = (
            FailureReason.ROTATED_TABLE if is_rotated
            else FailureReason.NO_TABLE_FOUND
        )
        detail = (
            f"{'旋转表格：' if is_rotated else ''}四级提取均失败。"
            f"已尝试：{', '.join(attempted_methods)}"
        )
        parse_report.add_failure(paper, reason, detail, attempted_methods)
        logger.warning(f"[FAILED] 全部失败：{paper.title[:50]}")
        return False

    async def extract_all(
        self,
        papers: list[PaperRecord],
        domain: str,
        max_concurrent: int = 3,
    ) -> tuple[list[PaperRecord], ParseReport]:
        """
        批量提取所有论文的指标分数。

        Args:
            papers:         论文列表（来自 Phase 2 输出）
            domain:         研究领域
            max_concurrent: 最大并发数（建议 3，Docling 较占内存）

        Returns:
            (updated_papers, parse_report)
        """
        parse_report = ParseReport(
            domain=domain,
            total_papers=len(papers),
        )

        semaphore = asyncio.Semaphore(max_concurrent)

        async def extract_with_sem(paper: PaperRecord) -> bool:
            async with semaphore:
                success = await self.extract_one(paper, domain, parse_report)
                if success:
                    parse_report.success_count += 1
                return success

        logger.info(
            f"表格解析开始：{len(papers)} 篇论文，并发数 {max_concurrent}"
        )
        tasks = [extract_with_sem(p) for p in papers]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(
            f"表格解析完成：成功 {parse_report.success_count}/"
            f"{parse_report.total_papers}，"
            f"失败 {parse_report.failure_count} 篇"
        )
        return papers, parse_report

    async def _download_pdf(self, paper: PaperRecord) -> Optional[str]:
        """下载 PDF 到本地缓存目录"""
        import aiohttp

        pdf_dir = Path(self.settings.PDF_DOWNLOAD_DIR)
        pdf_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r'[^\w\-]', '_', paper.paper_id or paper.title[:30])
        local_path = pdf_dir / f"{safe_name}.pdf"

        if local_path.exists():
            return str(local_path)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    paper.pdf_url,
                    timeout=aiohttp.ClientTimeout(total=60),
                    headers={"User-Agent": "SOD-COD-Research-Assistant/1.0"},
                ) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        local_path.write_bytes(content)
                        logger.info(f"PDF 下载成功：{local_path}")
                        return str(local_path)
        except Exception as e:
            logger.error(f"PDF 下载失败：{paper.pdf_url} -> {e}")
        return None

    def _get_local_pdf_path(self, paper: PaperRecord) -> Optional[str]:
        """检查 PDF 是否已下载到本地"""
        pdf_dir   = Path(self.settings.PDF_DOWNLOAD_DIR)
        safe_name = re.sub(r'[^\w\-]', '_', paper.paper_id or paper.title[:30])
        local_path = pdf_dir / f"{safe_name}.pdf"
        return str(local_path) if local_path.exists() else None
