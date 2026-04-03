"""
fetcher 包 - Agent1 第二层：PDF 获取层（Phase 2 实现）

五级优先级瀑布流：
  优先级1: S2 openAccessPdf 字段（已由搜索层填充，直接使用）
  优先级2: arXiv 直链构造（arxiv.org/pdf/{id}）
  优先级3: CVF/NeurIPS 顶会开放库直链
  优先级4: Unpaywall API（按 DOI 查询，需提供邮箱）
  优先级5: CORE API（终极兜底，可选，需 API Key）
"""

from .pdf_fetcher       import PDFFetcher, FetchResult, FetchStats
from .arxiv_fetcher     import ArXivFetcher
from .conference_fetcher import ConferenceFetcher
from .unpaywall_fetcher import UnpywallFetcher
from .core_fetcher      import COREFetcher

__all__ = [
    "PDFFetcher",
    "FetchResult",
    "FetchStats",
    "ArXivFetcher",
    "ConferenceFetcher",
    "UnpywallFetcher",
    "COREFetcher",
]
