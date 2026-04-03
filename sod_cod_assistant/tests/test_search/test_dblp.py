"""
DBLP 搜索器单元测试

测试范围：
  1. _parse_hit         - DBLP hit 数据解析
  2. _extract_authors   - 多种格式作者提取
  3. search_by_venue_and_keyword - 按期刊/关键词搜索（Mock HTTP）
  4. search             - 完整搜索流程（Mock HTTP）
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from typing import Any, Dict, List

from agents.agent1_sota.search.dblp import DBLPSearcher
from shared.models import PaperSource


# ── 测试数据 ──────────────────────────────────────────────────────────

MOCK_DBLP_HIT_MULTI_AUTHOR: Dict[str, Any] = {
    "@score": "8",
    "@id": "journals/tpami/ZhangW23",
    "info": {
        "authors": {
            "author": [
                {"@pid": "001", "text": "Zheng Lin"},
                {"@pid": "002", "text": "Wei Wang"},
            ]
        },
        "title": "Camouflaged Object Detection with Frequency-Guided Feature Fusion",
        "venue": "TPAMI",
        "year": "2023",
        "type": "Journal Articles",
        "doi": "10.1109/TPAMI.2023.3123456",
        "url": "https://dblp.org/rec/journals/tpami/ZhangW23",
    },
}

MOCK_DBLP_HIT_SINGLE_AUTHOR: Dict[str, Any] = {
    "@score": "5",
    "@id": "conf/cvpr/Wang24",
    "info": {
        "authors": {"author": {"@pid": "003", "text": "Jane Doe"}},
        "title": "Salient Object Detection via Vision Transformer",
        "venue": "CVPR",
        "year": "2024",
        "type": "Conference and Workshop Papers",
        "url": "https://dblp.org/rec/conf/cvpr/Wang24",
    },
}

MOCK_DBLP_HIT_CORR: Dict[str, Any] = {
    "@score": "3",
    "@id": "journals/corr/abs-2401-12345",
    "info": {
        "authors": {"author": "Anonymous"},
        "title": "Preprint on Camouflaged Detection",
        "venue": "CoRR",  # 预印本，应被过滤
        "year": "2024",
        "type": "Informal and Other Publications",
        "url": "https://arxiv.org/abs/2401.12345",
    },
}

MOCK_DBLP_RESPONSE: Dict[str, Any] = {
    "result": {
        "hits": {
            "@total": "2",
            "hit": [MOCK_DBLP_HIT_MULTI_AUTHOR, MOCK_DBLP_HIT_SINGLE_AUTHOR],
        }
    }
}

MOCK_DBLP_CORR_RESPONSE: Dict[str, Any] = {
    "result": {
        "hits": {
            "@total": "1",
            "hit": [MOCK_DBLP_HIT_CORR],
        }
    }
}

MOCK_DBLP_EMPTY_RESPONSE: Dict[str, Any] = {
    "result": {
        "hits": {}
    }
}

CVPR_VENUE_INFO = {
    "full_name": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
    "type": "conference",
    "ccf_rank": "A",
    "sci_tier": "N/A",
    "impact_factor": None,
    "dblp_key": "conf/cvpr",
}

TPAMI_VENUE_INFO = {
    "full_name": "IEEE Transactions on Pattern Analysis and Machine Intelligence",
    "type": "journal",
    "ccf_rank": "A",
    "sci_tier": "Q1",
    "impact_factor": 23.6,
    "dblp_key": "journals/pami",
}


# ── 单元测试 ──────────────────────────────────────────────────────────

class TestExtractAuthors:
    """测试 DBLP 多格式作者提取"""

    def test_list_of_dicts(self) -> None:
        """多作者（字典列表格式）"""
        authors_raw = {
            "author": [
                {"text": "Alice Smith"},
                {"text": "Bob Jones"},
            ]
        }
        result = DBLPSearcher._extract_authors(authors_raw)
        assert result == ["Alice Smith", "Bob Jones"]

    def test_single_dict(self) -> None:
        """单作者（字典格式）"""
        authors_raw = {"author": {"text": "Carol White"}}
        result = DBLPSearcher._extract_authors(authors_raw)
        assert result == ["Carol White"]

    def test_single_string(self) -> None:
        """单作者（字符串格式）"""
        authors_raw = {"author": "Dave Brown"}
        result = DBLPSearcher._extract_authors(authors_raw)
        assert result == ["Dave Brown"]

    def test_list_of_strings(self) -> None:
        """多作者（字符串列表）"""
        authors_raw = {"author": ["Eve Green", "Frank Blue"]}
        result = DBLPSearcher._extract_authors(authors_raw)
        assert result == ["Eve Green", "Frank Blue"]

    def test_empty_input(self) -> None:
        """空输入应返回空列表"""
        assert DBLPSearcher._extract_authors({}) == []
        assert DBLPSearcher._extract_authors(None) == []


class TestParseHit:
    """测试 DBLP hit 解析"""

    def setup_method(self) -> None:
        self.searcher = DBLPSearcher()

    def test_parse_multi_author_hit(self) -> None:
        """多作者论文应正确解析"""
        paper = self.searcher._parse_hit(
            MOCK_DBLP_HIT_MULTI_AUTHOR, "IEEE TPAMI", TPAMI_VENUE_INFO
        )
        assert paper is not None
        assert paper.title == "Camouflaged Object Detection with Frequency-Guided Feature Fusion"
        assert paper.year == 2023
        assert len(paper.authors) == 2
        assert "Zheng Lin" in paper.authors
        assert paper.doi == "10.1109/tpami.2023.3123456"
        assert paper.venue == "IEEE TPAMI"
        assert paper.ccf_rank == "A"
        assert paper.sci_tier == "Q1"
        assert PaperSource.DBLP in paper.found_by

    def test_parse_single_author_hit(self) -> None:
        """单作者会议论文应正确解析"""
        paper = self.searcher._parse_hit(
            MOCK_DBLP_HIT_SINGLE_AUTHOR, "CVPR", CVPR_VENUE_INFO
        )
        assert paper is not None
        assert paper.title == "Salient Object Detection via Vision Transformer"
        assert paper.year == 2024
        assert paper.authors == ["Jane Doe"]
        assert paper.ccf_rank == "A"

    def test_parse_corr_venue_filtered(self) -> None:
        """CoRR（arXiv 预印本）应被过滤返回 None"""
        paper = self.searcher._parse_hit(
            MOCK_DBLP_HIT_CORR, "CoRR", {}
        )
        assert paper is None

    def test_parse_old_year_filtered(self) -> None:
        """2019 年以前的论文应被过滤"""
        hit = {
            **MOCK_DBLP_HIT_MULTI_AUTHOR,
            "info": {**MOCK_DBLP_HIT_MULTI_AUTHOR["info"], "year": "2018"},
        }
        paper = self.searcher._parse_hit(hit, "IEEE TPAMI", TPAMI_VENUE_INFO)
        assert paper is None

    def test_parse_empty_info(self) -> None:
        """空 info 字段应返回 None"""
        paper = self.searcher._parse_hit({}, "CVPR", CVPR_VENUE_INFO)
        assert paper is None


@pytest.mark.asyncio
class TestDBLPSearch:
    """测试 DBLP 搜索流程（Mock HTTP）"""

    @pytest.fixture
    def searcher(self) -> DBLPSearcher:
        return DBLPSearcher()

    async def test_search_by_venue_returns_papers(
        self, searcher: DBLPSearcher
    ) -> None:
        """正常响应应解析出论文列表"""
        with patch.object(
            searcher, "_make_request", new_callable=AsyncMock,
            return_value=MOCK_DBLP_RESPONSE,
        ):
            papers = await searcher.search_by_venue_and_keyword(
                venue_name="IEEE TPAMI",
                venue_info=TPAMI_VENUE_INFO,
                keyword="camouflaged object detection",
            )
        # 两条记录中，CORR 被过滤（MOCK_DBLP_RESPONSE 不含 CoRR）
        assert len(papers) == 2
        assert all(p.year >= 2019 for p in papers)

    async def test_search_by_venue_filters_corr(
        self, searcher: DBLPSearcher
    ) -> None:
        """CoRR 条目应被过滤"""
        with patch.object(
            searcher, "_make_request", new_callable=AsyncMock,
            return_value=MOCK_DBLP_CORR_RESPONSE,
        ):
            papers = await searcher.search_by_venue_and_keyword(
                venue_name="CVPR",
                venue_info=CVPR_VENUE_INFO,
                keyword="camouflaged object detection",
            )
        assert papers == []

    async def test_search_by_venue_empty_hits(
        self, searcher: DBLPSearcher
    ) -> None:
        """空结果应返回空列表"""
        with patch.object(
            searcher, "_make_request", new_callable=AsyncMock,
            return_value=MOCK_DBLP_EMPTY_RESPONSE,
        ):
            papers = await searcher.search_by_venue_and_keyword(
                venue_name="CVPR",
                venue_info=CVPR_VENUE_INFO,
                keyword="some nonexistent query",
            )
        assert papers == []

    async def test_search_by_venue_api_failure(
        self, searcher: DBLPSearcher
    ) -> None:
        """API 失败时应返回空列表"""
        with patch.object(
            searcher, "_make_request", new_callable=AsyncMock, return_value=None
        ):
            papers = await searcher.search_by_venue_and_keyword(
                venue_name="CVPR",
                venue_info=CVPR_VENUE_INFO,
                keyword="camouflaged object detection",
            )
        assert papers == []

    async def test_full_search_returns_result(
        self, searcher: DBLPSearcher
    ) -> None:
        """完整 search() 应返回 SearchResult"""
        with patch.object(
            searcher, "_make_request", new_callable=AsyncMock,
            return_value=MOCK_DBLP_RESPONSE,
        ):
            result = await searcher.search("COD")

        assert result.source == PaperSource.DBLP
        assert result.domain == "COD"
        assert isinstance(result.papers, list)
