"""
全局配置模块 - 从 .env 文件读取所有配置项并暴露为类型安全的配置对象。

使用方式：
    from config.settings import settings
    print(settings.SEMANTIC_SCHOLAR_API_KEY)
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from dotenv import dotenv_values

logger = logging.getLogger(__name__)

# 直接从 .env 文件读取键值（不经过 os.environ，彻底规避 conda 环境变量干扰）
_env_path = Path(__file__).parent.parent / ".env"
_env_file_values: dict[str, str | None] = dotenv_values(dotenv_path=_env_path)


def _get_val(key: str, default: str = "") -> str:
    """
    优先读取 .env 文件中的值，其次才读取系统环境变量。
    过滤掉未替换的占位符（如 'your_xxx_here'）。
    """
    val = _env_file_values.get(key) or ""
    if not val:
        val = os.getenv(key, default)
    return val.strip() if val else default


class Settings:
    """
    项目全局配置类。
    通过 dotenv_values 直接读取 .env 文件，
    不受 conda 环境变量或系统环境变量干扰。
    """

    _PLACEHOLDERS = frozenset({
        "your_s2_api_key_here",
        "your_openalex_api_key_here",
        "your_email@example.com",
        "your_unpaywall_email@example.com",
        "your_core_api_key_here",
        "your_xxx_here",
        "",
    })

    def __init__(self) -> None:
        # ── Semantic Scholar ────────────────────────────────────────
        s2_key = _get_val("SEMANTIC_SCHOLAR_API_KEY")
        self.SEMANTIC_SCHOLAR_API_KEY: str = (
            "" if s2_key in self._PLACEHOLDERS else s2_key
        )
        if not self.SEMANTIC_SCHOLAR_API_KEY:
            logger.warning(
                "[Settings] [W] SEMANTIC_SCHOLAR_API_KEY 未配置。"
                "系统将以无 Key 模式运行（速率受限）。"
                "申请地址：https://www.semanticscholar.org/product/api#api-key-form"
            )

        # ── OpenAlex ─────────────────────────────────────────────────
        oa_key = _get_val("OPENALEX_API_KEY")
        self.OPENALEX_API_KEY: str = (
            "" if oa_key in self._PLACEHOLDERS else oa_key
        )
        if not self.OPENALEX_API_KEY:
            logger.warning(
                "[Settings] [W] OPENALEX_API_KEY 未配置。"
                "OpenAlex 将以 polite pool（邮箱）模式运行。"
                "申请地址：https://openalex.org/settings/api"
            )

        oa_email = _get_val("OPENALEX_EMAIL")
        self.OPENALEX_EMAIL: str = (
            "" if oa_email in self._PLACEHOLDERS else oa_email
        )

        # ── Unpaywall ────────────────────────────────────────────────
        un_email = _get_val("UNPAYWALL_EMAIL")
        self.UNPAYWALL_EMAIL: str = (
            "" if un_email in self._PLACEHOLDERS else un_email
        )

        # ── CORE API（可选，PDF 获取兜底）────────────────────────────
        core_key = _get_val("CORE_API_KEY")
        self.CORE_API_KEY: str = (
            "" if core_key in self._PLACEHOLDERS else core_key
        )

        # ── 激活的 AI 提供商：claude 或 openai ──────────────────────────
        self.ACTIVE_AI_PROVIDER: str = _get_val("ACTIVE_AI_PROVIDER", "claude")

        # ── Anthropic / Claude ────────────────────────────────────────
        claude_key = _get_val("ANTHROPIC_API_KEY")
        self.ANTHROPIC_API_KEY: str = (
            "" if claude_key in self._PLACEHOLDERS else claude_key
        )
        self.ANTHROPIC_BASE_URL: str = _get_val("ANTHROPIC_BASE_URL", "")
        self.ANTHROPIC_MODEL: str = _get_val(
            "ANTHROPIC_MODEL", "claude-sonnet-4-6"
        )
        self.VISION_MODEL: str = _get_val("VISION_MODEL", "")

        # ── OpenAI / Codex ────────────────────────────────────────────
        openai_key = _get_val("OPENAI_API_KEY")
        self.OPENAI_API_KEY: str = (
            "" if openai_key in self._PLACEHOLDERS else openai_key
        )
        self.OPENAI_BASE_URL: str = _get_val("OPENAI_BASE_URL", "")
        self.OPENAI_MODEL: str = _get_val("OPENAI_MODEL", "gpt-5.4")

        # ── Agent2 叙述报告配置 ────────────────────────────────────────
        # 可选：你当前研究方案的一句话描述，Agent2 会据此生成针对性建议
        # 示例："基于Mamba骨干网络的COD方法，引入判别器驱动的自适应路由模块，
        #        在CAMO/COD10K/NC4K三个数据集上达到SOTA水平"
        self.USER_METHOD_DESC: str = _get_val("USER_METHOD_DESC", "")

        # ── Agent3 代码分析配置 ────────────────────────────────────────
        self.GITHUB_TOKEN:          str = _get_val("GITHUB_TOKEN", "")
        self.AGENT3_MAX_CONCURRENT: int = self._parse_int(
            _get_val("AGENT3_MAX_CONCURRENT"), 3
        )

        # ── 搜索行为配置 ──────────────────────────────────────────────
        self.SEARCH_REQUEST_DELAY: float = self._parse_float(
            _get_val("SEARCH_REQUEST_DELAY"), 1.0
        )
        self.SEARCH_MAX_RESULTS_PER_SOURCE: int = self._parse_int(
            _get_val("SEARCH_MAX_RESULTS_PER_SOURCE"), 50
        )
        self.SEARCH_TIMEOUT: int = self._parse_int(
            _get_val("SEARCH_TIMEOUT"), 30
        )
        # 论文年份下限（只保留该年份及以后的论文）
        self.SEARCH_MIN_YEAR: int = self._parse_int(
            _get_val("SEARCH_MIN_YEAR"), 2024
        )
        # 最低 Venue Tier（1=只要CCF-A/Q1；2=含CCF-B/Q2）
        self.VENUE_MIN_TIER: int = self._parse_int(
            _get_val("VENUE_MIN_TIER"), 1
        )

        # ── PDF 获取层配置 ────────────────────────────────────────────
        self.FETCH_MAX_CONCURRENT: int = self._parse_int(
            _get_val("FETCH_MAX_CONCURRENT"), 5
        )
        self.FETCH_TIMEOUT: int = self._parse_int(
            _get_val("FETCH_TIMEOUT"), 15
        )
        self.PDF_DOWNLOAD_DIR: str = _get_val("PDF_DOWNLOAD_DIR", "cache/pdfs")

        # ── 缓存目录 ──────────────────────────────────────────────────
        self.CACHE_DIR: str = _get_val("CACHE_DIR", "cache/sota_cache")
        Path(self.CACHE_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.PDF_DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

        # ── Phase 3 解析层配置 ────────────────────────────────────────
        # 表格解析最大并发数（Docling 较占内存，建议 3）
        self.PARSE_MAX_CONCURRENT: int = self._parse_int(
            _get_val("PARSE_MAX_CONCURRENT"), 3
        )
        # 是否启用 VLM 兜底（消耗 API 额度，默认开启）
        self.ENABLE_VLM_FALLBACK: bool = (
            _get_val("ENABLE_VLM_FALLBACK", "true").lower() != "false"
        )
        # 排行榜 + 失败报告输出目录（默认与缓存目录相同）
        self.PARSE_OUTPUT_DIR: str = _get_val(
            "PARSE_OUTPUT_DIR", self.CACHE_DIR
        )
        Path(self.PARSE_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _parse_float(raw: str, default: float) -> float:
        try:
            return float(raw) if raw else default
        except ValueError:
            return default

    @staticmethod
    def _parse_int(raw: str, default: int) -> int:
        try:
            return int(raw) if raw else default
        except ValueError:
            return default

    def print_status(self) -> None:
        """打印当前 API Key 配置状态。"""
        _masked = lambda k: f"{k[:6]}...{k[-4:]}" if len(k) > 12 else "***"

        print("=" * 60)
        print("[Config] SOD/COD 科研助手 - 配置状态")
        print("=" * 60)
        print(f"  Semantic Scholar Key : "
              f"{'[OK] ' + _masked(self.SEMANTIC_SCHOLAR_API_KEY) if self.SEMANTIC_SCHOLAR_API_KEY else '[--] 未配置（无 Key 降级模式）'}")
        print(f"  OpenAlex Key         : "
              f"{'[OK] ' + _masked(self.OPENALEX_API_KEY) if self.OPENALEX_API_KEY else '[!!] 未配置（使用 email polite pool）'}")
        print(f"  OpenAlex Email       : "
              f"{'[OK] ' + self.OPENALEX_EMAIL if self.OPENALEX_EMAIL else '[--] 未填写'}")
        print(f"  Unpaywall Email      : "
              f"{'[OK] ' + self.UNPAYWALL_EMAIL if self.UNPAYWALL_EMAIL else '[--] 未填写'}")
        print(f"  CORE API Key         : "
              f"{'[OK] ' + _masked(self.CORE_API_KEY) if self.CORE_API_KEY else '[--] 未配置（CORE 兜底跳过）'}")
        print(f"  Claude API Key       : "
              f"{'[OK] ' + _masked(self.ANTHROPIC_API_KEY) if self.ANTHROPIC_API_KEY else '[--] 未配置（VLM 兜底跳过）'}")
        print(f"  Claude Base URL      : "
              f"{self.ANTHROPIC_BASE_URL if self.ANTHROPIC_BASE_URL else '（使用官方地址）'}")
        print(f"  Claude Model         : {self.ANTHROPIC_MODEL}")
        print(f"  Vision Model         : "
              f"{self.VISION_MODEL if self.VISION_MODEL else '（未设置，使用 ANTHROPIC_MODEL）'}")
        print(f"  搜索请求间隔         : {self.SEARCH_REQUEST_DELAY} 秒")
        print(f"  每源最大结果数       : {self.SEARCH_MAX_RESULTS_PER_SOURCE} 篇")
        print(f"  论文年份下限         : {self.SEARCH_MIN_YEAR} 年")
        print(f"  Venue 最低 Tier      : {self.VENUE_MIN_TIER} "
              f"({'仅 CCF-A/Q1' if self.VENUE_MIN_TIER == 1 else '含 CCF-B/Q2'})")
        print(f"  PDF 并发数           : {self.FETCH_MAX_CONCURRENT}")
        print(f"  PDF 目录             : {self.PDF_DOWNLOAD_DIR}")
        print(f"  缓存目录             : {self.CACHE_DIR}")
        print(f"  解析并发数           : {self.PARSE_MAX_CONCURRENT}")
        print(f"  VLM 兜底             : {'开启' if self.ENABLE_VLM_FALLBACK else '关闭'}")
        print(f"  排行榜输出目录       : {self.PARSE_OUTPUT_DIR}")
        print(f"  .env 路径            : {_env_path} ({'存在' if _env_path.exists() else '不存在!'})")
        print("=" * 60)


# 全局单例
settings = Settings()


# ── 各 Agent 输出目录（按日期自动创建子文件夹）────────────────────────
def get_agent_output_dir(agent_num: int) -> str:
    """
    获取指定 Agent 的今日输出目录，不存在则自动创建。

    Args:
        agent_num: Agent 编号（1/2/3/4）；0 表示主控 Agent（master 目录）

    Returns:
        形如 "cache/agent1/2026-03-12" 或 "cache/master/2026-03-12" 的路径字符串

    用法：
        from config.settings import get_agent_output_dir
        out_dir = get_agent_output_dir(2)   # → "cache/agent2/2026-03-12"
        out_dir = get_agent_output_dir(0)   # → "cache/master/2026-03-12"
    """
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    name  = "master" if agent_num == 0 else f"agent{agent_num}"
    path  = Path(settings.CACHE_DIR).parent / name / today
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
