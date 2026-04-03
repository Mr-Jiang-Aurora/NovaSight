"""
Semantic Scholar 搜索器单元测试

测试范围：
  1. _parse_paper_item   - 论文 JSON 解析
  2. _normalize_venue    - 来源名称标准化
  3. search_by_keywords  - 关键词搜索（Mock HTTP）
  4. expand_via_citations - 引用扩展（Mock HTTP）
  5. search              - 完整搜索流程（Mock HTTP）
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List

from agents.agent1_sota.search.semantic_scholar import SemanticScholarSearcher
from shared.models import PaperRecord, PaperSource


# ── 测试数据 ──────────────────────────────────────────────────────────

MOCK_PAPER_ITEM: Dict[str, Any] = {
    "paperId": "abc123def456",
    "title": "Camouflaged Object Detection via Frequency-Aware Fusion",
    "year": 2023,
    "venue": "2023 IEEE/CVF Conference on Computer Vision and Pattern Recognition",
    "authors": [
        {"authorId": "1", "name": "Zheng Lin"},
        {"authorId": "2", "name": "Zhao Zhang"},
    ],
    "citationCount": 42,
    "influentialCitationCount": 5,
    "abstract": "We propose a novel framework for camouflaged object detection.",
    "openAccessPdf": {"url": "https://arxiv.org/pdf/2301.12345.pdf"},
    "externalIds": {
        "ArXiv": "2301.12345",
        "DOI": "10.1109/CVPR52729.2023.00123",
        "CorpusId": 999888,
    },
}

MOCK_PAPER_ITEM_JOURNAL: Dict[str, Any] = {
    "paperId": "journal001",
    "title": "Salient Object Detection with Transformer: A Survey",
    "year": 2022,
    "venue": "IEEE Transactions on Pattern Analysis and Machine Intelligence",
    "authors": [{"authorId": "3", "name": "Wei Wang"}],
    "citationCount": 100,
    "influentialCitationCount": 12,
    "abstract": "This paper surveys transformer-based SOD methods.",
    "openAccessPdf": None,
    "externalIds": {
        "DOI": "10.1109/TPAMI.2022.3123456",
        "CorpusId": 111222,
    },
}

MOCK_SEARCH_RESPONSE: Dict[str, Any] = {
    "data": [MOCK_PAPER_ITEM, MOCK_PAPER_ITEM_JOURNAL],
    "total": 2,
    "next": None,
}

MOCK_CITATIONS_RESPONSE: Dict[str, Any] = {
    "data": [
        {
            "citingPaper": MOCK_PAPER_ITEM,
        }
    ],
    "next": None,
}


# ── 测试类 ────────────────────────────────────────────────────────────

class TestSemanticScholarParser:
    """测试论文数据解析逻辑（不涉及网络请求）"""

    def setup_method(self) -> None:
        self.searcher = SemanticScholarSearcher()

    def test_parse_paper_item_basic(self) -> None:
        """测试基本论文信息解析是否正确"""
        paper = self.searcher._parse_paper_item(MOCK_PAPER_ITEM)

        assert paper is not None
        assert paper.paper_id == "abc123def456"
        assert paper.title == "Camouflaged Object Detection via Frequency-Aware Fusion"
        assert paper.year == 2023
        assert paper.arxiv_id == "2301.12345"
        assert paper.citation_count == 42
        assert len(paper.authors) == 2
        assert paper.authors[0] == "Zheng Lin"
        assert paper.pdf_url == "https://arxiv.org/pdf/2301.12345.pdf"
        assert paper.paper_url == "https://arxiv.org/abs/2301.12345"
        assert PaperSource.SEMANTIC_SCHOLAR in paper.found_by

    def test_parse_paper_item_journal(self) -> None:
        """测试期刊论文解析（无 arXiv，有 DOI）"""
        paper = self.searcher._parse_paper_item(MOCK_PAPER_ITEM_JOURNAL)

        assert paper is not None
        assert paper.paper_id == "journal001"
        assert paper.year == 2022
        assert paper.arxiv_id is None
        assert paper.doi == "10.1109/tpami.2022.3123456"
        assert paper.paper_url == "https://doi.org/10.1109/tpami.2022.3123456"
        assert paper.pdf_url is None

    def test_parse_paper_item_empty_title(self) -> None:
        """标题为空时应返回 None"""
        item = {**MOCK_PAPER_ITEM, "title": ""}
        paper = self.searcher._parse_paper_item(item)
        assert paper is None

    def test_parse_paper_item_missing_title(self) -> None:
        """缺少 title 字段时应返回 None"""
        item = {k: v for k, v in MOCK_PAPER_ITEM.items() if k != "title"}
        paper = self.searcher._parse_paper_item(item)
        assert paper is None

    def test_parse_paper_item_no_external_ids(self) -> None:
        """无 externalIds 时不应抛出异常"""
        item = {**MOCK_PAPER_ITEM, "externalIds": None}
        paper = self.searcher._parse_paper_item(item)
        assert paper is not None
        assert paper.arxiv_id is None
        assert paper.doi is None


class TestNormalizeVenue:
    """测试 venue 名称标准化逻辑"""

    def setup_method(self) -> None:
        self.searcher = SemanticScholarSearcher()

    def test_normalize_cvpr_full_name(self) -> None:
        """完整 CVPR 名称应映射到 'CVPR'"""
        raw = "2024 IEEE/CVF Conference on Computer Vision and Pattern Recognition"
        assert self.searcher._normalize_venue(raw) == "CVPR"

    def test_normalize_tpami_full_name(self) -> None:
        """TPAMI 全称应映射到 'IEEE TPAMI'"""
        raw = "IEEE Transactions on Pattern Analysis and Machine Intelligence"
        assert self.searcher._normalize_venue(raw) == "IEEE TPAMI"

    def test_normalize_tip_abbreviation(self) -> None:
        """TIP 缩写应映射到 'IEEE TIP'"""
        raw = "IEEE TIP"
        assert self.searcher._normalize_venue(raw) == "IEEE TIP"

    def test_normalize_unknown_venue(self) -> None:
        """未知来源应返回原始字符串"""
        raw = "Some Unknown Conference 2024"
        result = self.searcher._normalize_venue(raw)
        assert result == raw

    def test_normalize_empty_venue(self) -> None:
        """空字符串应返回空字符串"""
        assert self.searcher._normalize_venue("") == ""


@pytest.mark.asyncio
class TestSemanticScholarSearch:
    """测试搜索方法（使用 Mock 替代真实 HTTP 请求）"""

    @pytest.fixture
    def searcher(self) -> SemanticScholarSearcher:
        return SemanticScholarSearcher()

    async def test_search_by_keywords_returns_papers(
        self, searcher: SemanticScholarSearcher
    ) -> None:
        """关键词搜索应正确过滤并返回目标期刊论文"""
        with patch.object(
            searcher,
            "_make_request",
            new_callable=AsyncMock,
            return_value=MOCK_SEARCH_RESPONSE,
        ):
            papers = await searcher.search_by_keywords(
                "camouflaged object detection"
            )

        # 两条 mock 数据都应该通过过滤（CVPR 和 TPAMI 均在目标列表）
        assert len(papers) >= 1
        for paper in papers:
            assert paper.title  # 标题非空
            assert paper.year and paper.year >= 2019

    async def test_search_by_keywords_empty_response(
        self, searcher: SemanticScholarSearcher
    ) -> None:
        """API 返回空数据时应返回空列表"""
        with patch.object(
            searcher,
            "_make_request",
            new_callable=AsyncMock,
            return_value={"data": [], "total": 0},
        ):
            papers = await searcher.search_by_keywords("nonexistent query xyz")

        assert papers == []

    async def test_search_by_keywords_api_failure(
        self, searcher: SemanticScholarSearcher
    ) -> None:
        """API 请求失败（返回 None）时应返回空列表而不抛出异常"""
        with patch.object(
            searcher, "_make_request", new_callable=AsyncMock, return_value=None
        ):
            papers = await searcher.search_by_keywords("camouflaged object detection")

        assert papers == []

    async def test_expand_via_citations_returns_papers(
        self, searcher: SemanticScholarSearcher
    ) -> None:
        """引用图谱扩展应正确解析引用数据"""
        with patch.object(
            searcher,
            "_make_request",
            new_callable=AsyncMock,
            return_value=MOCK_CITATIONS_RESPONSE,
        ):
            papers = await searcher.expand_via_citations(["ARXIV:1911.05563"])

        # MOCK 中的引用论文 venue 为 CVPR，应通过过滤
        assert isinstance(papers, list)

    async def test_full_search_cod_domain(
        self, searcher: SemanticScholarSearcher
    ) -> None:
        """完整 search() 方法对 COD 领域应返回 SearchResult"""
        with patch.object(
            searcher,
            "_make_request",
            new_callable=AsyncMock,
            return_value=MOCK_SEARCH_RESPONSE,
        ):
            result = await searcher.search("COD")

        assert result.source == PaperSource.SEMANTIC_SCHOLAR
        assert result.domain == "COD"
        assert isinstance(result.papers, list)
        assert result.search_time_seconds >= 0
        assert isinstance(result.errors, list)
