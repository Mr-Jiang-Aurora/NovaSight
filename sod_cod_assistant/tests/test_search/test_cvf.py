"""
CVF Open Access 爬取器单元测试

测试范围：
  1. _build_url             - URL 构建（新旧格式）
  2. _build_domain_keywords - 关键词集合构建
  3. _title_matches_domain  - 标题关键词匹配
  4. _parse_conference_page - HTML 页面解析
  5. scrape_conference      - 爬取流程（Mock HTTP）
  6. search                 - 完整搜索（Mock HTTP）
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Any, Dict, Set

from agents.agent1_sota.search.cvf_open_access import CVFSearcher, CVF_BASE_URL
from config.knowledge_base import get_domain_info
from shared.models import PaperSource


# ── 测试 HTML（模拟 CVF 页面片段）────────────────────────────────────

MOCK_CVF_HTML = """
<!DOCTYPE html>
<html>
<body>
<dl>
  <dt class="ptitle">
    <a href="/content/CVPR2023/html/Lin_Camouflaged_Object_Detection_With_Feature_Decomposition_CVPR_2023_paper.html">
      Camouflaged Object Detection With Feature Decomposition and Edge Reconstruction
    </a>
  </dt>
  <dd>
    <div class="authors">
      Zheng Lin, Xiankai Lu, Wei-Shi Zheng
    </div>
    <div class="links">
      <a href="/content/CVPR2023/papers/Lin_Camouflaged_Object_Detection_CVPR_2023_paper.pdf">pdf</a>
      <a href="https://arxiv.org/abs/2301.12345">arXiv</a>
    </div>
  </dd>

  <dt class="ptitle">
    <a href="/content/CVPR2023/html/Wang_Salient_Object_Detection_CVPR_2023_paper.html">
      Salient Object Detection via Context-Aware Feature Aggregation
    </a>
  </dt>
  <dd>
    <div class="authors">
      Wei Wang, Jia Li
    </div>
    <div class="links">
      <a href="/content/CVPR2023/papers/Wang_Salient_Object_Detection_CVPR_2023_paper.pdf">pdf</a>
    </div>
  </dd>

  <dt class="ptitle">
    <a href="/content/CVPR2023/html/Some_Unrelated_Paper.html">
      3D Scene Understanding with Point Cloud Networks
    </a>
  </dt>
  <dd>
    <div class="authors">Bob Smith</div>
    <div class="links">
      <a href="/content/CVPR2023/papers/unrelated.pdf">pdf</a>
    </div>
  </dd>
</dl>
</body>
</html>
"""

CVPR_VENUE_INFO = {
    "full_name": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
    "type": "conference",
    "ccf_rank": "A",
    "sci_tier": "N/A",
    "impact_factor": None,
    "cvf_name": "CVPR",
}


# ── 单元测试 ──────────────────────────────────────────────────────────

class TestBuildUrl:
    """测试 CVF URL 构建（新旧两种格式）"""

    def setup_method(self) -> None:
        self.searcher = CVFSearcher()

    def test_url_2021_and_after_uses_day_all(self) -> None:
        """2021年及以后应使用 ?day=all 格式"""
        url = self.searcher._build_url("CVPR", 2021)
        assert url == f"{CVF_BASE_URL}/CVPR2021?day=all"

    def test_url_2022_uses_day_all(self) -> None:
        url = self.searcher._build_url("CVPR", 2022)
        assert url == f"{CVF_BASE_URL}/CVPR2022?day=all"

    def test_url_2023_uses_day_all(self) -> None:
        url = self.searcher._build_url("ICCV", 2023)
        assert url == f"{CVF_BASE_URL}/ICCV2023?day=all"

    def test_url_2020_uses_py_suffix(self) -> None:
        """2020年及以前应使用 .py 后缀格式"""
        url = self.searcher._build_url("CVPR", 2020)
        assert url == f"{CVF_BASE_URL}/CVPR2020.py"

    def test_url_2019_uses_py_suffix(self) -> None:
        url = self.searcher._build_url("CVPR", 2019)
        assert url == f"{CVF_BASE_URL}/CVPR2019.py"


class TestBuildDomainKeywords:
    """测试领域关键词集合构建"""

    def test_cod_keywords_not_empty(self) -> None:
        """COD 领域应生成非空关键词集合"""
        domain_info = get_domain_info("COD")
        keywords = CVFSearcher._build_domain_keywords(domain_info)
        assert len(keywords) > 0

    def test_cod_keywords_contain_camouflaged(self) -> None:
        """COD 领域关键词应包含 'camouflaged'"""
        domain_info = get_domain_info("COD")
        keywords = CVFSearcher._build_domain_keywords(domain_info)
        assert "camouflaged" in keywords

    def test_sod_keywords_contain_salient(self) -> None:
        """SOD 领域关键词应包含 'salient'"""
        domain_info = get_domain_info("SOD")
        keywords = CVFSearcher._build_domain_keywords(domain_info)
        assert "salient" in keywords

    def test_cod_keywords_include_datasets(self) -> None:
        """关键词应包含 COD 数据集名称（小写）"""
        domain_info = get_domain_info("COD")
        keywords = CVFSearcher._build_domain_keywords(domain_info)
        # COD10K、CAMO 等数据集名应包含在关键词中
        assert any(
            ds.lower() in keywords
            for ds in domain_info["datasets"]
        )


class TestTitleMatchesDomain:
    """测试标题关键词匹配逻辑"""

    COD_KEYWORDS: Set[str] = {
        "camouflaged", "concealed", "cod10k", "camo", "chameleon"
    }
    SOD_KEYWORDS: Set[str] = {
        "salient", "saliency", "duts", "ecssd"
    }

    def test_cod_title_matches(self) -> None:
        title = "Camouflaged Object Detection With Feature Decomposition"
        assert CVFSearcher._title_matches_domain(title, self.COD_KEYWORDS)

    def test_concealed_title_matches(self) -> None:
        title = "Concealed Object Detection via Edge-Guided Refinement"
        assert CVFSearcher._title_matches_domain(title, self.COD_KEYWORDS)

    def test_sod_title_matches(self) -> None:
        title = "Salient Object Detection via Context-Aware Feature Aggregation"
        assert CVFSearcher._title_matches_domain(title, self.SOD_KEYWORDS)

    def test_unrelated_title_not_matches(self) -> None:
        title = "3D Scene Understanding with Point Cloud Networks"
        assert not CVFSearcher._title_matches_domain(title, self.COD_KEYWORDS)

    def test_case_insensitive(self) -> None:
        """匹配应大小写不敏感"""
        title = "CAMOUFLAGED OBJECT DETECTION SURVEY"
        assert CVFSearcher._title_matches_domain(title, self.COD_KEYWORDS)


class TestParseConferencePage:
    """测试 CVF HTML 页面解析"""

    def setup_method(self) -> None:
        self.searcher = CVFSearcher()
        self.cod_keywords = {"camouflaged", "concealed", "cod10k", "salient", "saliency"}

    def test_parses_cod_paper(self) -> None:
        """应解析出 COD 相关论文"""
        papers = self.searcher._parse_conference_page(
            html_content=MOCK_CVF_HTML,
            conf_name="CVPR",
            year=2023,
            domain_keywords=self.cod_keywords,
            venue_name="CVPR",
            venue_info=CVPR_VENUE_INFO,
        )
        # 应找到 camouflaged 和 salient 两篇（第三篇不相关）
        assert len(papers) >= 1
        titles = [p.title for p in papers]
        assert any("Camouflaged" in t for t in titles)

    def test_filters_unrelated_papers(self) -> None:
        """无关论文（3D 场景）应被过滤"""
        papers = self.searcher._parse_conference_page(
            html_content=MOCK_CVF_HTML,
            conf_name="CVPR",
            year=2023,
            domain_keywords=self.cod_keywords,
            venue_name="CVPR",
            venue_info=CVPR_VENUE_INFO,
        )
        titles = [p.title for p in papers]
        assert not any("3D Scene" in t for t in titles)

    def test_extracts_arxiv_id(self) -> None:
        """应从 arXiv 链接提取 arXiv ID"""
        papers = self.searcher._parse_conference_page(
            html_content=MOCK_CVF_HTML,
            conf_name="CVPR",
            year=2023,
            domain_keywords=self.cod_keywords,
            venue_name="CVPR",
            venue_info=CVPR_VENUE_INFO,
        )
        camouflaged_papers = [
            p for p in papers if "Camouflaged" in p.title
        ]
        assert len(camouflaged_papers) == 1
        assert camouflaged_papers[0].arxiv_id == "2301.12345"

    def test_extracts_pdf_url(self) -> None:
        """应正确拼接 PDF URL"""
        papers = self.searcher._parse_conference_page(
            html_content=MOCK_CVF_HTML,
            conf_name="CVPR",
            year=2023,
            domain_keywords=self.cod_keywords,
            venue_name="CVPR",
            venue_info=CVPR_VENUE_INFO,
        )
        camouflaged_papers = [p for p in papers if "Camouflaged" in p.title]
        assert len(camouflaged_papers) == 1
        assert camouflaged_papers[0].pdf_url is not None
        assert camouflaged_papers[0].pdf_url.startswith(CVF_BASE_URL)
        assert camouflaged_papers[0].pdf_url.endswith(".pdf")

    def test_correct_year_and_venue(self) -> None:
        """年份和 venue 应正确赋值"""
        papers = self.searcher._parse_conference_page(
            html_content=MOCK_CVF_HTML,
            conf_name="CVPR",
            year=2023,
            domain_keywords=self.cod_keywords,
            venue_name="CVPR",
            venue_info=CVPR_VENUE_INFO,
        )
        for p in papers:
            assert p.year == 2023
            assert p.venue == "CVPR"
            assert p.ccf_rank == "A"
            assert PaperSource.CVF_OPEN_ACCESS in p.found_by

    def test_empty_html(self) -> None:
        """空 HTML 应返回空列表（不抛出异常）"""
        papers = self.searcher._parse_conference_page(
            html_content="<html><body></body></html>",
            conf_name="CVPR",
            year=2023,
            domain_keywords=self.cod_keywords,
            venue_name="CVPR",
            venue_info=CVPR_VENUE_INFO,
        )
        assert papers == []


@pytest.mark.asyncio
class TestCVFScrape:
    """测试 CVF 完整爬取流程（Mock HTTP）"""

    @pytest.fixture
    def searcher(self) -> CVFSearcher:
        return CVFSearcher()

    async def test_scrape_conference_success(
        self, searcher: CVFSearcher
    ) -> None:
        """成功爬取应返回过滤后的论文"""
        cod_keywords = {"camouflaged", "concealed", "salient", "saliency"}
        with patch.object(
            searcher, "_fetch_html", new_callable=AsyncMock,
            return_value=MOCK_CVF_HTML,
        ):
            papers = await searcher.scrape_conference(
                conf_name="CVPR",
                years=[2023],
                domain_keywords=cod_keywords,
                venue_name="CVPR",
                venue_info=CVPR_VENUE_INFO,
            )
        assert len(papers) >= 1

    async def test_scrape_conference_404(
        self, searcher: CVFSearcher
    ) -> None:
        """页面不存在（返回 None）时应跳过不抛出异常"""
        with patch.object(
            searcher, "_fetch_html", new_callable=AsyncMock, return_value=None
        ):
            papers = await searcher.scrape_conference(
                conf_name="ICCV",
                years=[2022],  # ICCV 2022 未举办
                domain_keywords={"camouflaged"},
                venue_name="ICCV",
                venue_info={"full_name": "ICCV", "ccf_rank": "A"},
            )
        assert papers == []

    async def test_full_search_returns_result(
        self, searcher: CVFSearcher
    ) -> None:
        """完整 search() 应返回 SearchResult"""
        with patch.object(
            searcher, "_fetch_html", new_callable=AsyncMock,
            return_value=MOCK_CVF_HTML,
        ):
            result = await searcher.search("COD")

        assert result.source == PaperSource.CVF_OPEN_ACCESS
        assert result.domain == "COD"
        assert isinstance(result.papers, list)
        assert result.search_time_seconds >= 0
