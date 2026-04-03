"""
期刊/会议的分区和影响因子静态映射表。
数据来源：2024年中科院分区 + CCF 2022推荐目录。
"""

# 格式：{venue_key: {ccf, cas_tier, if_2023, full_name}}
# ccf: A/B/C/-
# cas_tier: Q1/Q2/Q3/Q4/-（中科院分区）
# if_2023: 影响因子（2023年）

VENUE_INFO: dict = {
    # ── 顶级期刊 ──────────────────────────────────────────────────────
    "TPAMI": {
        "full_name": "IEEE Transactions on Pattern Analysis and Machine Intelligence",
        "ccf": "A", "cas_tier": "Q1", "if_2023": 23.6,
    },
    "IJCV": {
        "full_name": "International Journal of Computer Vision",
        "ccf": "A", "cas_tier": "Q1", "if_2023": 19.5,
    },
    "TIP": {
        "full_name": "IEEE Transactions on Image Processing",
        "ccf": "A", "cas_tier": "Q1", "if_2023": 10.8,
    },
    "TNNLS": {
        "full_name": "IEEE Transactions on Neural Networks and Learning Systems",
        "ccf": "B", "cas_tier": "Q1", "if_2023": 14.3,
    },
    "TMM": {
        "full_name": "IEEE Transactions on Multimedia",
        "ccf": "B", "cas_tier": "Q1", "if_2023": 8.4,
    },
    "TCSVT": {
        "full_name": "IEEE Transactions on Circuits and Systems for Video Technology",
        "ccf": "B", "cas_tier": "Q1", "if_2023": 8.4,
    },
    "PR": {
        "full_name": "Pattern Recognition",
        "ccf": "B", "cas_tier": "Q1", "if_2023": 8.0,
    },
    "KBS": {
        "full_name": "Knowledge-Based Systems",
        "ccf": "C", "cas_tier": "Q1", "if_2023": 7.2,
    },
    "NN": {
        "full_name": "Neural Networks",
        "ccf": "B", "cas_tier": "Q1", "if_2023": 6.0,
    },
    "ESWA": {
        "full_name": "Expert Systems with Applications",
        "ccf": "C", "cas_tier": "Q1", "if_2023": 7.5,
    },
    "NEUCOM": {
        "full_name": "Neurocomputing",
        "ccf": "C", "cas_tier": "Q2", "if_2023": 6.0,
    },
    "SIGNAL": {
        "full_name": "Signal Processing",
        "ccf": "C", "cas_tier": "Q2", "if_2023": 4.4,
    },
    # ── 顶级会议 ──────────────────────────────────────────────────────
    "CVPR": {
        "full_name": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        "ccf": "A", "cas_tier": "-", "if_2023": None,
    },
    "ICCV": {
        "full_name": "International Conference on Computer Vision",
        "ccf": "A", "cas_tier": "-", "if_2023": None,
    },
    "ECCV": {
        "full_name": "European Conference on Computer Vision",
        "ccf": "B", "cas_tier": "-", "if_2023": None,
    },
    "NeurIPS": {
        "full_name": "Advances in Neural Information Processing Systems",
        "ccf": "A", "cas_tier": "-", "if_2023": None,
    },
    "ICLR": {
        "full_name": "International Conference on Learning Representations",
        "ccf": "-", "cas_tier": "-", "if_2023": None,
    },
    "AAAI": {
        "full_name": "AAAI Conference on Artificial Intelligence",
        "ccf": "A", "cas_tier": "-", "if_2023": None,
    },
    "ICML": {
        "full_name": "International Conference on Machine Learning",
        "ccf": "A", "cas_tier": "-", "if_2023": None,
    },
    "ACM MM": {
        "full_name": "ACM International Conference on Multimedia",
        "ccf": "A", "cas_tier": "-", "if_2023": None,
    },
    "IJCAI": {
        "full_name": "International Joint Conference on Artificial Intelligence",
        "ccf": "A", "cas_tier": "-", "if_2023": None,
    },
    "WACV": {
        "full_name": "IEEE/CVF Winter Conference on Applications of Computer Vision",
        "ccf": "-", "cas_tier": "-", "if_2023": None,
    },
}


def get_venue_info(venue_str: str) -> dict:
    """
    根据 venue 字符串查询分区信息。
    优先精确 key 匹配，再按 full_name 模糊匹配。

    Returns:
        包含 ccf, cas_tier, if_2023, full_name 的字典
    """
    if not venue_str:
        return {"ccf": "-", "cas_tier": "-", "if_2023": None, "full_name": ""}

    venue_upper = venue_str.upper().strip()

    # arXiv 特判（优先，避免被其他规则误匹配）
    if "ARXIV" in venue_upper or "CORR" in venue_upper:
        return {"ccf": "-", "cas_tier": "-", "if_2023": None, "full_name": "arXiv Preprint"}

    # 阶段1：精确 key 匹配（整词）
    for key, info in VENUE_INFO.items():
        key_up = key.upper()
        # 完整单词匹配：key 作为完整词出现在 venue_upper 中
        import re as _re
        if _re.search(r'(?<![A-Z])' + _re.escape(key_up) + r'(?![A-Z])', venue_upper):
            return info

    # 阶段2：full_name 子串匹配
    for key, info in VENUE_INFO.items():
        if info["full_name"].upper() in venue_upper or venue_upper in info["full_name"].upper():
            return info

    return {
        "ccf":       "-",
        "cas_tier":  "-",
        "if_2023":   None,
        "full_name": venue_str,
        "_matched":  False,   # 标记为未匹配，供后续统计和提示使用
    }
