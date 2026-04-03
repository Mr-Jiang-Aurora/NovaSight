"""
parser 包 — Agent1 第三层：表格解析层（Phase 3 完整实现）

两阶段定位 + 四级分级提取策略：
  阶段1（定位）: PageLocator — 关键词扫描定位候选页
  阶段2（提取）:
    级别 A: Ar5ivParser   — ar5iv HTML 结构化解析（最准确）
    级别 B: PyMuPDFParser — PyMuPDF 规则提取（简单边框表格）
    级别 C: DoclingParser — Docling 深度识别（复杂无边框表格）
    级别 D: VLMParser     — Claude Vision VLM 兜底（旋转/图片内嵌表格）

调度入口: TableExtractor — 按序尝试四级，命中即停
输出层:   ReportGenerator — 生成排行榜 JSON/Markdown + 失败报告
验证层:   MetricExtractor — 数值范围验证 + 写入 PaperRecord.scores
"""

from .page_locator     import PageLocator
from .ar5iv_parser     import Ar5ivParser
from .pymupdf_parser   import PyMuPDFParser
from .docling_parser   import DoclingParser
from .vlm_parser       import VLMParser
from .metric_extractor import MetricExtractor
from .table_extractor  import TableExtractor
from .report_generator import ReportGenerator

__all__ = [
    "PageLocator",
    "Ar5ivParser",
    "PyMuPDFParser",
    "DoclingParser",
    "VLMParser",
    "MetricExtractor",
    "TableExtractor",
    "ReportGenerator",
]
