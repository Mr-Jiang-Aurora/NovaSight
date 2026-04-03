"""
SOD/COD 科研助手 - 通用工具函数

包含：
    - 标题归一化（用于去重比较）
    - 日志初始化
    - arXiv ID 提取
    - 时间戳生成
"""

from __future__ import annotations

import re
import logging
import sys
import unicodedata
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
# 1. 日志初始化
# ─────────────────────────────────────────────────────────────────────

def setup_logging(
    level: int = logging.INFO,
    log_format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    date_format: str = "%Y-%m-%d %H:%M:%S",
) -> None:
    """
    初始化项目级日志配置。
    建议在程序入口（agent1_main.py 或 scripts/）调用一次。
    """
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # 降低第三方库的日志噪音
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ─────────────────────────────────────────────────────────────────────
# 2. 标题归一化（用于去重比较）
# ─────────────────────────────────────────────────────────────────────

def normalize_title(title: str) -> str:
    """
    将论文标题归一化，用于去重比较。
    
    处理步骤：
    1. Unicode NFKC 规范化（处理全角字符等）
    2. 转小写
    3. 去除标点和特殊字符（只保留字母、数字、空格）
    4. 压缩连续空格
    5. strip
    
    Args:
        title: 原始论文标题
    
    Returns:
        归一化后的字符串，适合用 == 或 difflib 比较
    
    Examples:
        >>> normalize_title("SINet: Search-and-Identification Network")
        "sinet search and identification network"
        >>> normalize_title("RGB-D Salient Object Detection: A Survey")
        "rgbd salient object detection a survey"
    """
    if not title:
        return ""
    
    # Unicode 规范化，将全角转半角等
    normalized = unicodedata.normalize("NFKC", title)
    
    # 转小写
    normalized = normalized.lower()
    
    # 去除标点、特殊字符，只保留字母数字和空格
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    
    # 压缩连续空格并 strip
    normalized = re.sub(r"\s+", " ", normalized).strip()
    
    return normalized


def title_similarity(title1: str, title2: str) -> float:
    """
    计算两个标题的相似度（0-1 之间）。
    使用 difflib.SequenceMatcher，归一化后比较。
    
    Returns:
        相似度比例，>= 0.92 视为重复
    """
    import difflib
    
    t1 = normalize_title(title1)
    t2 = normalize_title(title2)
    
    if not t1 or not t2:
        return 0.0
    
    if t1 == t2:
        return 1.0
    
    return difflib.SequenceMatcher(None, t1, t2).ratio()


# ─────────────────────────────────────────────────────────────────────
# 3. arXiv ID 提取与规范化
# ─────────────────────────────────────────────────────────────────────

# arXiv ID 有两种格式：
#   旧格式：hep-th/9901001
#   新格式（2007年后）：1234.5678 或 1234.56789
_ARXIV_PATTERN = re.compile(
    r"(?:arxiv[:\s]*)?"                      # 可选的 "arxiv:" 前缀
    r"((?:[a-z\-]+/\d{7}|\d{4}\.\d{4,5}))"  # 捕获 arXiv ID
    r"(?:v\d+)?",                             # 可选的版本号（忽略）
    re.IGNORECASE
)


def extract_arxiv_id(text: str) -> Optional[str]:
    """
    从 URL、字符串中提取 arXiv ID，并规范化为不含版本号的形式。
    
    Args:
        text: 可能包含 arXiv ID 的字符串，如 URL、DOI、raw ID
    
    Returns:
        规范化的 arXiv ID（如 "2301.12345"），或 None

    Examples:
        >>> extract_arxiv_id("https://arxiv.org/abs/2301.12345v2")
        "2301.12345"
        >>> extract_arxiv_id("ARXIV:1911.05563")
        "1911.05563"
    """
    if not text:
        return None
    
    match = _ARXIV_PATTERN.search(text)
    if match:
        return match.group(1).lower()
    
    return None


def normalize_doi(doi: str) -> Optional[str]:
    """
    规范化 DOI 字符串，去除 URL 前缀，转小写。
    
    Args:
        doi: 原始 DOI，如 "https://doi.org/10.1109/TPAMI.2023.1234" 或 "10.1109/..."
    
    Returns:
        规范化的 DOI（如 "10.1109/tpami.2023.1234"），或 None
    """
    if not doi:
        return None
    
    # 去除常见 DOI URL 前缀
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = doi.strip().lower()
    
    # 基本验证：DOI 必须以 "10." 开头
    if not doi.startswith("10."):
        return None
    
    return doi


# ─────────────────────────────────────────────────────────────────────
# 4. 时间戳与文件命名工具
# ─────────────────────────────────────────────────────────────────────

def get_timestamp() -> str:
    """
    返回当前时间的紧凑格式时间戳字符串，用于文件命名。
    格式：YYYYMMDD_HHMMSS
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_filename(name: str, max_length: int = 64) -> str:
    """
    将任意字符串转换为安全的文件名（去除特殊字符）。
    
    Args:
        name:       原始字符串
        max_length: 最大长度限制
    
    Returns:
        安全的文件名字符串
    """
    # 只保留字母、数字、连字符、下划线
    safe = re.sub(r"[^\w\-]", "_", name)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe[:max_length]


# ─────────────────────────────────────────────────────────────────────
# 5. 字符串清理工具
# ─────────────────────────────────────────────────────────────────────

def clean_author_name(name: str) -> str:
    """清理作者姓名，去除多余空格和非打印字符。"""
    if not name:
        return ""
    return re.sub(r"\s+", " ", name).strip()


def truncate_abstract(abstract: str, max_chars: int = 500) -> str:
    """截断摘要到指定字符数，保持词边界。"""
    if not abstract or len(abstract) <= max_chars:
        return abstract
    
    truncated = abstract[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.8:
        truncated = truncated[:last_space]
    
    return truncated + "..."
