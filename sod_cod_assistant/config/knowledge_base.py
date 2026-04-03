"""
SOD/COD 科研助手领域知识库
包含：数据集配置、指标别名映射、监控期刊列表、CCF/SCI 分级信息
"""

from typing import Dict, List, Any


# ─────────────────────────────────────────────────────────────────────
# 1. 领域数据集与指标配置
# ─────────────────────────────────────────────────────────────────────

DOMAIN_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "COD": {
        "full_name": "Camouflaged Object Detection",
        "chinese_name": "伪装目标检测",
        "datasets": ["COD10K", "CAMO", "NC4K", "CHAMELEON"],
        "primary_dataset": "COD10K",   # 排行榜主排序数据集
        "metrics": ["Sm", "Em", "Fm", "MAE", "Fβ"],
        "primary_metric": "Sm",        # 主排序指标
        "page_keywords": [
            "Table", "benchmark", "comparison",
            "state-of-the-art", "competing methods",
            "COD10K", "CAMO", "NC4K", "CHAMELEON"
        ],
        "valid_ranges": {
            "Sm":  [0.60, 1.00],
            "Em":  [0.60, 1.00],
            "Fm":  [0.00, 1.00],
            "MAE": [0.001, 0.20]
        },
        # S2 搜索关键词组合
        "search_queries": [
            "camouflaged object detection",
            "concealed object detection",
            "camouflaged object segmentation",
            "background-foreground ambiguity detection",
        ],
        # 领域奠基论文 S2 ID（用于引用图谱扩展）
        "seed_paper_ids": [
            "ARXIV:1911.05563",   # SINet (COD10K 数据集论文)
            "ARXIV:2011.11616",   # PFNet
            "ARXIV:2108.00086",   # C2FNet
            "ARXIV:2207.02083",   # ERPNet
        ]
    },

    "SOD": {
        "full_name": "Salient Object Detection",
        "chinese_name": "显著性目标检测",
        "datasets": ["DUTS-TE", "HKU-IS", "ECSSD", "PASCAL-S", "DUT-OMRON"],
        "primary_dataset": "DUTS-TE",
        "metrics": ["Sm", "Em", "Fm", "MAE", "maxFm", "avgFm"],
        "primary_metric": "Sm",
        "page_keywords": [
            "Table", "benchmark", "comparison",
            "DUTS", "HKU-IS", "ECSSD", "PASCAL-S", "DUT-OMRON"
        ],
        "valid_ranges": {
            "Sm":    [0.70, 1.00],
            "Em":    [0.70, 1.00],
            "Fm":    [0.00, 1.00],
            "MAE":   [0.001, 0.15],
            "maxFm": [0.00, 1.00],
            "avgFm": [0.00, 1.00]
        },
        "search_queries": [
            "salient object detection",
            "saliency detection deep learning",
            "visual saliency detection",
            "salient region detection",
        ],
        "seed_paper_ids": [
            "ARXIV:1907.06781",   # PoolNet
            "ARXIV:2005.11366",   # MINet
            "ARXIV:2101.10925",   # VST
        ]
    },

    "RGB-D SOD": {
        "full_name": "RGB-D Salient Object Detection",
        "chinese_name": "RGB-D显著性目标检测",
        "datasets": ["NJUD", "NLPR", "DUT-RGBD", "SIP", "STERE"],
        "primary_dataset": "NJUD",
        "metrics": ["Sm", "Em", "Fm", "MAE"],
        "primary_metric": "Sm",
        "page_keywords": [
            "Table", "benchmark", "comparison",
            "NJUD", "NLPR", "DUT-RGBD", "SIP", "STERE", "depth"
        ],
        "valid_ranges": {
            "Sm":  [0.70, 1.00],
            "Em":  [0.70, 1.00],
            "Fm":  [0.00, 1.00],
            "MAE": [0.001, 0.15]
        },
        "search_queries": [
            "RGB-D salient object detection",
            "depth salient object detection",
            "RGBD saliency detection",
        ],
        "seed_paper_ids": []
    },

    "RGBT SOD": {
        "full_name": "RGB-T Salient Object Detection",
        "chinese_name": "RGB-T显著性目标检测",
        "datasets": ["VT821", "VT1000", "VT5000"],
        "primary_dataset": "VT5000",
        "metrics": ["Sm", "Em", "Fm", "MAE"],
        "primary_metric": "Sm",
        "page_keywords": [
            "Table", "benchmark", "comparison",
            "VT821", "VT1000", "VT5000", "thermal", "infrared"
        ],
        "valid_ranges": {
            "Sm":  [0.60, 1.00],
            "Em":  [0.60, 1.00],
            "Fm":  [0.00, 1.00],
            "MAE": [0.001, 0.20]
        },
        "search_queries": [
            "RGB-T salient object detection",
            "thermal infrared salient object detection",
            "visible thermal salient detection",
        ],
        "seed_paper_ids": []
    }
}


# ─────────────────────────────────────────────────────────────────────
# 2. 指标名称别名映射表（用于模糊识别与标准化）
# ─────────────────────────────────────────────────────────────────────

METRIC_ALIAS_MAP: Dict[str, List[str]] = {
    "Sm": [
        "sm", "s-measure", "smeasure", "s_m", "sα", "sa",
        "structure measure", "structuremeasure", "structurem",
        "sm↑", "s_measure", "s measure", "smeas",
        "structure similarity", "structural measure"
    ],
    "Em": [
        "em", "e-measure", "emeasure", "e_m", "eξ", "ex", "exi",
        "enhanced-fm", "enhanced fm", "φem", "em↑", "e_measure",
        "e measure", "enhanced alignment", "emeas",
        "enhanced-alignment measure"
    ],
    "Fm": [
        "fm", "f-measure", "fmeasure", "f_β", "fβ", "fb",
        "weighted f", "wfm", "fw", "maxf", "avgf", "meanf",
        "fm↑", "f_measure", "f measure", "fmeas",
        "weighted fm", "f-score", "fbeta"
    ],
    "MAE": [
        "mae", "m", "mae↓", "mean absolute error", "meanae",
        "absolute error", "mean_absolute_error", "mae_score",
        "mean_error", "average absolute error", "aae"
    ],
    "maxFm": [
        "maxfm", "max-fm", "max_fm", "max f-measure",
        "max fm", "maximum fm", "max f", "fm_max"
    ],
    "avgFm": [
        "avgfm", "avg-fm", "avg_fm", "avg f-measure",
        "avg fm", "average fm", "mean fm", "fm_avg", "meanfm"
    ]
}


# ─────────────────────────────────────────────────────────────────────
# 3. 监控期刊/会议列表（双层 Tier 系统）
#    Tier 1：CCF-A + SCI Q1（核心，强制保留）
#    Tier 2：CCF-B + SCI Q1/Q2（次要，可配置保留）
# ─────────────────────────────────────────────────────────────────────

MONITORED_VENUES: Dict[str, Dict[str, Any]] = {
    # ── Tier 1：CCF-A + SCI Q1（核心，强制保留）─────────────────────
    "IEEE TPAMI": {
        "full_name": "IEEE Transactions on Pattern Analysis and Machine Intelligence",
        "type": "journal",
        "ccf_rank": "A",
        "sci_tier": "Q1",
        "tier": 1,
        "impact_factor": 23.6,
        "publisher": "IEEE",
        "dblp_key": "journals/pami",
        "dblp_venue_query": "TPAMI",
        "search_in_s2": True,
        "search_in_openalex": True,
    },
    "IEEE TIP": {
        "full_name": "IEEE Transactions on Image Processing",
        "type": "journal",
        "ccf_rank": "A",
        "sci_tier": "Q1",
        "tier": 1,
        "impact_factor": 10.9,
        "publisher": "IEEE",
        "dblp_key": "journals/tip",
        "dblp_venue_query": "TIP",
        "search_in_s2": True,
        "search_in_openalex": True,
    },
    "IJCV": {
        "full_name": "International Journal of Computer Vision",
        "type": "journal",
        "ccf_rank": "A",
        "sci_tier": "Q1",
        "tier": 1,
        "impact_factor": 11.4,
        "publisher": "Springer",
        "dblp_key": "journals/ijcv",
        "dblp_venue_query": "IJCV",
        "search_in_s2": True,
        "search_in_openalex": True,
    },
    "CVPR": {
        "full_name": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        "type": "conference",
        "ccf_rank": "A",
        "sci_tier": "N/A",
        "tier": 1,
        "impact_factor": None,
        "publisher": "CVF/IEEE",
        "dblp_key": "conf/cvpr",
        "cvf_name": "CVPR",
        "held_every_year": True,
        "typical_month": 6,
        "search_in_s2": True,
        "search_in_dblp": True,
        "search_in_cvf": True,
    },
    "ICCV": {
        "full_name": "IEEE/CVF International Conference on Computer Vision",
        "type": "conference",
        "ccf_rank": "A",
        "sci_tier": "N/A",
        "tier": 1,
        "impact_factor": None,
        "publisher": "CVF/IEEE",
        "dblp_key": "conf/iccv",
        "cvf_name": "ICCV",
        "held_every_year": False,
        "held_years": [2021, 2023, 2025, 2027],
        "typical_month": 10,
        "search_in_s2": True,
        "search_in_dblp": True,
        "search_in_cvf": True,
    },
    "NeurIPS": {
        "full_name": "Conference on Neural Information Processing Systems",
        "type": "conference",
        "ccf_rank": "A",
        "sci_tier": "N/A",
        "tier": 1,
        "impact_factor": None,
        "publisher": "NeurIPS Foundation",
        "dblp_key": "conf/nips",
        "cvf_name": None,
        "held_every_year": True,
        "typical_month": 12,
        "search_in_s2": True,
        "search_in_dblp": True,
        "search_in_cvf": False,
    },
    "AAAI": {
        "full_name": "AAAI Conference on Artificial Intelligence",
        "type": "conference",
        "ccf_rank": "A",
        "sci_tier": "N/A",
        "tier": 1,
        "impact_factor": None,
        "publisher": "AAAI Press",
        "dblp_key": "conf/aaai",
        "cvf_name": None,
        "held_every_year": True,
        "typical_month": 2,
        "search_in_s2": True,
        "search_in_dblp": True,
        "search_in_cvf": False,
    },
    "ICML": {
        "full_name": "International Conference on Machine Learning",
        "type": "conference",
        "ccf_rank": "A",
        "sci_tier": "N/A",
        "tier": 1,
        "impact_factor": None,
        "publisher": "PMLR",
        "dblp_key": "conf/icml",
        "cvf_name": None,
        "held_every_year": True,
        "typical_month": 7,
        "search_in_s2": True,
        "search_in_dblp": True,
        "search_in_cvf": False,
    },

    # ── Tier 2：CCF-B + SCI Q1/Q2（次要，可配置保留）────────────────
    "PR": {
        "full_name": "Pattern Recognition",
        "type": "journal",
        "ccf_rank": "B",
        "sci_tier": "Q1",
        "tier": 2,
        "impact_factor": 7.5,
        "publisher": "Elsevier",
        "dblp_key": "journals/pr",
        "dblp_venue_query": "Pattern Recognition",
        "search_in_s2": True,
        "search_in_openalex": True,
    },
    "IEEE TCSVT": {
        "full_name": "IEEE Transactions on Circuits and Systems for Video Technology",
        "type": "journal",
        "ccf_rank": "B",
        "sci_tier": "Q1",
        "tier": 2,
        "impact_factor": 8.4,
        "publisher": "IEEE",
        "dblp_key": "journals/tcsv",
        "dblp_venue_query": "TCSVT",
        "search_in_s2": True,
        "search_in_openalex": True,
    },
    "ECCV": {
        "full_name": "European Conference on Computer Vision",
        "type": "conference",
        "ccf_rank": "B",
        "sci_tier": "N/A",
        "tier": 2,
        "impact_factor": None,
        "publisher": "Springer",
        "dblp_key": "conf/eccv",
        "cvf_name": None,
        "held_every_year": False,
        "held_years": [2022, 2024, 2026, 2028],
        "typical_month": 10,
        "search_in_s2": True,
        "search_in_dblp": True,
        "search_in_cvf": False,
    },
}


# ─────────────────────────────────────────────────────────────────────
# 4. Venue 精确匹配与 Tier 辅助函数
# ─────────────────────────────────────────────────────────────────────

# 内部缓存，首次调用时构建
_VENUE_MATCH_PATTERNS: list[tuple[str, str]] = []

# 明确排除的噪音来源（子串精确匹配，优先于白名单检查）
_VENUE_BLACKLIST: list[str] = [
    "signal processing letters",
    "icassp",
    "ieee signal processing",
    "acoustics, speech",
    "speech and signal",
    "ieee transactions on signal",
    "journal of visual communication",
    "multimedia tools",
    "applied sciences",
    "sensors ",          # 注意尾部空格，避免误匹配 "sensors and"
    "electronics",
    "remote sensing letters",
    "neurocomputing",
    "knowledge-based systems",
    "expert systems",
    "neural networks",              # Elsevier Neural Networks（非顶刊）
    "neural computing",
    "image and vision computing",
    "computer vision and image",    # Computer Vision and Image Understanding
    "display",
    "optics express",
    "scientific reports",
    "plos one",
]


def _build_venue_patterns() -> None:
    """构建 Venue 精确匹配模式列表（首次调用时执行一次）"""
    global _VENUE_MATCH_PATTERNS
    if _VENUE_MATCH_PATTERNS:
        return
    patterns = []
    for key, info in MONITORED_VENUES.items():
        patterns.append((key.lower(), key))
        full = info.get("full_name", "").lower()
        if full:
            patterns.append((full, key))
        if info.get("cvf_name"):
            patterns.append((info["cvf_name"].lower(), key))
    # 按匹配串长度降序，保证优先匹配更长的模式（避免 "PR" 匹配到 "CVPR"）
    _VENUE_MATCH_PATTERNS = sorted(patterns, key=lambda x: len(x[0]), reverse=True)


def get_standard_venue_name(venue_name: str) -> str:
    """
    将各种写法的期刊/会议名称归并为标准简称。
    例如：
        "IEEE Trans. Pattern Anal." → "IEEE TPAMI"
        "CVPR 2024"                → "CVPR"
        "Proceedings of ICCV"      → "ICCV"
    未能识别时返回原始值；在黑名单中时返回 "BLACKLISTED"。
    """
    if not venue_name:
        return "Unknown"
    import re
    _build_venue_patterns()
    vl = venue_name.lower().strip()

    # 优先检查黑名单
    for blk in _VENUE_BLACKLIST:
        if blk in vl:
            return "BLACKLISTED"

    # 精确子串匹配（带词边界保护，避免 "PR" 匹配 "CVPR" 等）
    for pattern, std_name in _VENUE_MATCH_PATTERNS:
        if pattern in vl:
            idx = vl.find(pattern)
            before = vl[idx - 1] if idx > 0 else ' '
            after  = vl[idx + len(pattern)] if idx + len(pattern) < len(vl) else ' '
            if not before.isalpha() and not after.isalpha():
                return std_name

    # 顶会年份格式兜底（如 "CVPR2024"、"ICCV 2023"）
    for conf in ["CVPR", "ICCV", "ECCV", "AAAI", "NeurIPS", "NIPS", "ICML"]:
        if re.search(rf'\b{conf}\b', venue_name, re.IGNORECASE):
            return conf

    return venue_name


def get_venue_tier(venue_name: str) -> int:
    """
    返回期刊/会议的 Tier 等级：
        1 → CCF-A 或 SCI Q1（核心来源）
        2 → CCF-B 或 SCI Q2（次要来源）
        0 → 不在监控列表或在黑名单（应被过滤）

    Args:
        venue_name: 原始或标准化的期刊/会议名称

    Returns:
        int: 0 / 1 / 2
    """
    std = get_standard_venue_name(venue_name)
    if std in ("BLACKLISTED", "Unknown"):
        return 0
    info = MONITORED_VENUES.get(std, {})
    return info.get("tier", 0)


def is_target_venue(venue_name: str) -> bool:
    """
    向后兼容接口：判断是否在监控列表（Tier >= 1）。
    """
    return get_venue_tier(venue_name) >= 1


# ─────────────────────────────────────────────────────────────────────
# 5. 其他辅助函数
# ─────────────────────────────────────────────────────────────────────

# 指标标准名称映射表（供新版 normalize_metric_name 使用）
# key：论文中可能出现的各种写法（统一转小写后匹配）
# value：系统内部标准名称
_METRIC_ALIAS_MAP: Dict[str, str] = {
    # ── Sm（S-measure / Structure measure）────────────────────────────
    "sm":                    "Sm",
    "s-m":                   "Sm",
    "s_m":                   "Sm",
    "sα":                    "Sm",
    "sα↑":                   "Sm",
    "s_α":                   "Sm",
    "sa":                    "Sm",
    "s-measure":             "Sm",
    "smeasure":              "Sm",
    "s measure":             "Sm",
    "structure measure":     "Sm",
    "structure-measure":     "Sm",
    "structuremeasure":      "Sm",
    "structural measure":    "Sm",

    # ── Em（E-measure / Enhanced alignment measure）───────────────────
    "em":                    "Em",
    "e-m":                   "Em",
    "e_m":                   "Em",
    "eφ":                    "Em",
    "eφ↑":                   "Em",
    "eξ":                    "Em",
    "e_φ":                   "Em",
    "e-measure":             "Em",
    "emeasure":              "Em",
    "e measure":             "Em",
    "enhanced alignment":    "Em",
    "mean em":               "Em",
    "mean_em":               "Em",
    "meanem":                "Em",
    "φem":                   "Em",

    # ── MAE（Mean Absolute Error）─────────────────────────────────────
    "mae":                   "MAE",
    "mae↓":                  "MAE",
    "mean absolute error":   "MAE",
    "mean-absolute-error":   "MAE",
    "meanabsoluteerror":     "MAE",
    "mean ae":               "MAE",
    "meanae":                "MAE",
    "aae":                   "MAE",

    # ── Fm（F-measure / F-beta measure）──────────────────────────────
    "fm":                    "Fm",
    "f-m":                   "Fm",
    "f_m":                   "Fm",
    "fβ":                    "Fm",
    "fβ↑":                   "Fm",
    "f_β":                   "Fm",
    "fb":                    "Fm",
    "f-measure":             "Fm",
    "fmeasure":              "Fm",
    "f measure":             "Fm",
    "f-beta":                "Fm",
    "fbeta":                 "Fm",
    "f-score":               "Fm",
    "fscore":                "Fm",

    # ── maxFm（最大 F-measure）───────────────────────────────────────
    "maxfm":                 "maxFm",
    "max-fm":                "maxFm",
    "max_fm":                "maxFm",
    "maxfβ":                 "maxFm",
    "max-fβ":                "maxFm",
    "max f":                 "maxFm",
    "maximum fm":            "maxFm",
    "max fm":                "maxFm",
    "fm_max":                "maxFm",
    "maxf":                  "maxFm",

    # ── avgFm（平均 F-measure）───────────────────────────────────────
    "avgfm":                 "avgFm",
    "avg-fm":                "avgFm",
    "avg_fm":                "avgFm",
    "avgfβ":                 "avgFm",
    "mean fm":               "avgFm",
    "mean-fm":               "avgFm",
    "mean fβ":               "avgFm",
    "average fm":            "avgFm",
    "fm_avg":                "avgFm",
    "meanfm":                "avgFm",

    # ── wFm（weighted F-measure）─────────────────────────────────────
    "wfm":                   "wFm",
    "wf":                    "wFm",
    "w-fm":                  "wFm",
    "wfβ":                   "wFm",
    "wf_β":                  "wFm",
    "weighted fm":           "wFm",
    "weighted f":            "wFm",
    "weighted-fm":           "wFm",
    "weighted fmeasure":     "wFm",
    "wf↑":                   "wFm",
    "fw":                    "wFm",
}


def normalize_metric_name(raw_name: str) -> str:
    """
    将论文中出现的各种指标名称变体归一化为系统标准名称。

    处理步骤：
    1. 去除首尾空格和方向箭头（↑↓）
    2. 去除 LaTeX 上标语法（^{...}）
    3. 转小写查精确映射表
    4. 去除空格/连字符/下划线后再查（处理 "S measure" 等）
    5. 前缀匹配兜底

    Args:
        raw_name: 从 PDF/HTML 提取到的原始列名，如 "S_α↑"、"wF"、"MAE↓"

    Returns:
        标准名称（如 "Sm"/"Em"/"MAE"/"Fm"/"maxFm"/"avgFm"/"wFm"），
        无法识别时返回原始名称（不抛异常）
    """
    import re as _re

    if not raw_name:
        return raw_name

    # 去除首尾空格和换行
    cleaned = raw_name.strip()

    # 去除 Unicode 方向箭头
    cleaned = cleaned.replace("↑", "").replace("↓", "").strip()

    # 去除 LaTeX 上标语法：^{alpha} / ^α 等
    cleaned = _re.sub(r'\^\{?[\w\u0370-\u03FF]+\}?', '', cleaned)

    # 转小写进行查找
    key = cleaned.lower().strip()

    # 1. 精确匹配
    if key in _METRIC_ALIAS_MAP:
        return _METRIC_ALIAS_MAP[key]

    # 2. 去掉空格/连字符/下划线后再查
    key_compact = key.replace(" ", "").replace("-", "").replace("_", "")
    if key_compact in _METRIC_ALIAS_MAP:
        return _METRIC_ALIAS_MAP[key_compact]

    # 3. 前缀匹配（处理 "Smeasure(COD10K)" 这种带括号的列名）
    for alias, std in _METRIC_ALIAS_MAP.items():
        alias_compact = alias.replace(" ", "").replace("-", "").replace("_", "")
        if len(alias_compact) >= 2 and key_compact.startswith(alias_compact):
            return std

    # 4. 兼容旧版 METRIC_ALIAS_MAP（保证向后兼容）
    cleaned_legacy = (key
                      .replace('α', 'a').replace('β', 'b')
                      .replace('ξ', 'x').replace('φ', '')
                      .replace(' ', '').replace('-', '').replace('_', '')
                      .replace('^', ''))
    for std_name, aliases in METRIC_ALIAS_MAP.items():
        if cleaned_legacy in aliases:
            return std_name

    # 无法识别，返回原始名称
    return raw_name


def get_domain_info(domain: str) -> Dict[str, Any]:
    """
    获取指定领域的知识库配置。
    支持大小写不敏感和别名输入（如 "cod" → COD，"rgbd" → RGB-D SOD）
    """
    domain_map = {
        "cod": "COD",
        "camouflaged": "COD",
        "camouflaged object detection": "COD",
        "sod": "SOD",
        "salient": "SOD",
        "salient object detection": "SOD",
        "rgbd": "RGB-D SOD",
        "rgb-d": "RGB-D SOD",
        "rgb-d sod": "RGB-D SOD",
        "rgbt": "RGBT SOD",
        "rgb-t": "RGBT SOD",
        "rgb-t sod": "RGBT SOD",
    }
    normalized = domain_map.get(domain.lower().strip(), domain.upper())
    if normalized not in DOMAIN_KNOWLEDGE_BASE:
        raise ValueError(
            f"不支持的研究方向: '{domain}'。"
            f"支持的方向: {list(DOMAIN_KNOWLEDGE_BASE.keys())}"
        )
    return DOMAIN_KNOWLEDGE_BASE[normalized]


def get_venue_info(venue_name: str) -> Dict[str, Any]:
    """获取期刊/会议的 CCF 等级、SCI 分区及 Tier 信息。"""
    std = get_standard_venue_name(venue_name)
    return MONITORED_VENUES.get(std, {
        "ccf_rank": "Unknown",
        "sci_tier": "Unknown",
        "impact_factor": None,
        "tier": 0,
    })
