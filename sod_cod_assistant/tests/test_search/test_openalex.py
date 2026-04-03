"""
OpenAlex 搜索器单元测试

测试范围：
  1. _reconstruct_abstract   - 倒排索引重构摘要
  2. _parse_work_item        - OpenAlex Works 数据解析
  3. _normalize_venue        - 期刊名称标准化
  4. search_semantic         - 语义搜索（Mock HTTP）
  5. search                  - 完整搜索流程（Mock HTTP）
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from typing import Any, Dict, List, Optional

from agents.agent1_sota.search.openalex import OpenAlexSearcher
from shared.models import PaperSource


# ── 测试数据 ──────────────────────────────────────────────────────────

MOCK_ABSTRACT_INVERTED_INDEX: Dict[str, List[int]] = {
    "We": [0],
    "propose": [1],
    "a": [2, 7],
    "novel": [3],
    "method": [4],
    "for": [5],
    "camouflaged": [6],
    "detection": [8],
    "task.": [9],
}

MOCK_OA_WORK_ITEM: Dict[str, Any] = {
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.1109/CVPR52729.2023.00456",
    "display_name": "Frequency-Guided Feature Learning for Camouflaged Object Detection",
    "publication_year": 2023,
    "primary_location": {
        "source": {
            "display_name": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
            "type": "conference",
        }
    },
    "open_access": {
        "is_oa": True,
        "oa_url": "https://arxiv.org/pdf/2305.12345.pdf",
    },
    "best_oa_location": {
        "url": "https://arxiv.org/abs/2305.12345",
    },
    "abstract_inverted_index": MOCK_ABSTRACT_INVERTED_INDEX,
    "authorships": [
        {"author": {"display_name": "John Smith", "id": "A001"}},
        {"author": {"display_name": "Jane Doe",   "id": "A002"}},
    ],
    "cited_by_count": 35,
}

MOCK_OA_RESPONSE: Dict[str, Any] = {
    "results": [MOCK_OA_WORK_ITEM],
    "meta": {
        "count": 1,
        "next_cursor": None,
    },
}


# ── 单元测试 ──────────────────────────────────────────────────────────

class TestReconstructAbstract:
    """测试 OpenAlex 倒排索引摘要重构"""

    def test_basic_reconstruction(self) -> None:
        """正常倒排索引应重构为正确文本"""
        result = OpenAlexSearcher._reconstruct_abstract(
            MOCK_ABSTRACT_INVERTED_INDEX
        )
        assert result is not None
        # 验证词序正确（按位置排序后拼接）
        assert result.startswith("We propose")
        assert "camouflaged" in result
        assert "detection" in result

    def test_none_input(self) -> None:
        """None 输入应返回 None"""
        assert OpenAlexSearcher._reconstruct_abstract(None) is None

    def test_empty_dict(self) -> None:
        """空字典应返回 None"""
        assert OpenAlexSearcher._reconstruct_abstract({}) is None

    def test_single_word(self) -> None:
        """单词倒排索引应正确处理"""
        result = OpenAlexSearcher._reconstruct_abstract({"Hello": [0]})
        assert result == "Hello"

    def test_word_at_multiple_positions(self) -> None:
        """同一词出现在多个位置（如 'a'）应分别填入各位置"""
        index = {"the": [0, 4], "cat": [1], "and": [2], "dog": [3]}
        result = OpenAlexSearcher._reconstruct_abstract(index)
        words = result.split()
        assert words[0] == "the"
        assert words[4] == "the"
        assert "cat" in words
        assert "dog" in words


class TestParseWorkItem:
    """测试 OpenAlex Works 数据解析"""

    def setup_method(self) -> None:
        self.searcher = OpenAlexSearcher()

    def test_parse_basic_fields(self) -> None:
        """基本字段应正确解析"""
        paper = self.searcher._parse_work_item(MOCK_OA_WORK_ITEM)

        assert paper is not None
        assert paper.title == "Frequency-Guided Feature Learning for Camouflaged Object Detection"
        assert paper.year == 2023
        assert paper.doi == "10.1109/cvpr52729.2023.00456"
        assert paper.arxiv_id == "2305.12345"
        assert len(paper.authors) == 2
        assert "John Smith" in paper.authors
        assert paper.citation_count == 35
        assert PaperSource.OPENALEX in paper.found_by

    def test_parse_abstract_reconstruction(self) -> None:
        """摘要应从倒排索引正确重构"""
        paper = self.searcher._parse_work_item(MOCK_OA_WORK_ITEM)
        assert paper is not None
        assert paper.abstract is not None
        assert len(paper.abstract) > 0

    def test_parse_empty_title(self) -> None:
        """空标题应返回 None"""
        item = {**MOCK_OA_WORK_ITEM, "display_name": ""}
        paper = self.searcher._parse_work_item(item)
        assert paper is None

    def test_parse_missing_location(self) -> None:
        """无 primary_location 时不应抛出异常"""
        item = {**MOCK_OA_WORK_ITEM, "primary_location": None}
        paper = self.searcher._parse_work_item(item)
        assert paper is not None


class TestNormalizeVenueOA:
    """测试 OpenAlex venue 名称标准化"""

    def setup_method(self) -> None:
        self.searcher = OpenAlexSearcher()

    def test_cvpr_full_name(self) -> None:
        raw = "IEEE/CVF Conference on Computer Vision and Pattern Recognition"
        assert self.searcher._normalize_venue(raw) == "CVPR"

    def test_neurips_name(self) -> None:
        raw = "Conference on Neural Information Processing Systems"
        assert self.searcher._normalize_venue(raw) == "NeurIPS"

    def test_tpami_full(self) -> None:
        raw = "IEEE Transactions on Pattern Analysis and Machine Intelligence"
        assert self.searcher._normalize_venue(raw) == "IEEE TPAMI"

    def test_unknown_returns_original(self) -> None:
        raw = "Random Workshop on Stuff"
        assert self.searcher._normalize_venue(raw) == raw


@pytest.mark.asyncio
class TestOpenAlexSearch:
    """测试搜索流程（Mock HTTP）"""

    @pytest.fixture
    def searcher(self) -> OpenAlexSearcher:
        return OpenAlexSearcher()

    async def test_search_semantic_returns_papers(
        self, searcher: OpenAlexSearcher
    ) -> None:
        """语义搜索应返回过滤后的论文列表"""
        with patch.object(
            searcher, "_make_request", new_callable=AsyncMock,
            return_value=MOCK_OA_RESPONSE,
        ):
            papers = await searcher.search_semantic("camouflaged object detection")

        assert isinstance(papers, list)

    async def test_search_semantic_api_failure(
        self, searcher: OpenAlexSearcher
    ) -> None:
        """API 失败时应返回空列表"""
        with patch.object(
            searcher, "_make_request", new_callable=AsyncMock, return_value=None
        ):
            papers = await searcher.search_semantic("camouflaged object detection")

        assert papers == []

    async def test_full_search_returns_result(
        self, searcher: OpenAlexSearcher
    ) -> None:
        """完整 search() 方法应返回 SearchResult"""
        with patch.object(
            searcher, "_make_request", new_callable=AsyncMock,
            return_value=MOCK_OA_RESPONSE,
        ):
            result = await searcher.search("COD")

        assert result.source == PaperSource.OPENALEX
        assert result.domain == "COD"
        assert isinstance(result.papers, list)
        assert result.search_time_seconds >= 0
