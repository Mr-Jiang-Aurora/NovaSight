"""
论文 Figure 自动溯源器
从架构图识别结果中提取关键词，通过 Semantic Scholar API 搜索原论文。
"""

import asyncio
import logging
import math
import re
from typing import Optional, List
import aiohttp

logger = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = (
    "paperId,title,year,authors,venue,publicationVenue,"
    "citationCount,openAccessPdf,externalIds,"
    "abstract,fieldsOfStudy,s2FieldsOfStudy"
)


class FigureTracer:
    """论文 Figure 自动溯源器"""

    def __init__(self, api_key: str = ""):
        self.headers = {"User-Agent": "SOD-COD-Research-Assistant/1.0"}
        if api_key:
            self.headers["x-api-key"] = api_key

    async def trace(self, arch_hint, top_k: int = 5):
        """
        主入口：从 ArchHint 溯源论文。

        Args:
            arch_hint: Agent4 架构图解析结果（ArchHint 对象）
            top_k:     返回最多 top_k 篇候选论文

        Returns:
            FigureTraceResult 包含候选论文列表和置信度评估
        """
        from shared.models import FigureTraceResult

        result = FigureTraceResult(arch_hint_summary=arch_hint.structure_hint)

        # Step 1：从 ArchHint 提取搜索关键词
        queries = self._build_queries(arch_hint)
        result.search_queries = queries[:5]
        logger.info(f"[FigureTracer] 构建了 {len(queries)} 个搜索查询：{queries[:3]}")

        # Step 2：并发搜索所有查询
        all_candidates: list = []
        tasks = [self._search_one(q) for q in queries[:5]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"[FigureTracer] 搜索失败：{r}")
                continue
            all_candidates.extend(r)

        # Step 3：去重 + 相关性排序
        unique = self._deduplicate(all_candidates)
        ranked = self._rank_by_relevance(unique, arch_hint)[:top_k]
        result.candidates = ranked

        # Step 4：判断最可能的论文
        if ranked:
            result.best_match = ranked[0]
            result.confidence = self._assess_confidence(ranked[0], arch_hint)
            logger.info(
                f"[FigureTracer] 最佳匹配：{ranked[0].title[:50]} "
                f"（置信度={result.confidence}）"
            )

        # Step 5：生成溯源结论
        result.trace_summary = self._build_summary(result)
        return result

    def _build_queries(self, hint) -> List[str]:
        """
        从 ArchHint 构建多个搜索查询，按优先级从精确到宽泛排列。
        策略覆盖：decoder技术词 / backbone+任务 / 模块缩写 / venue提示词 / 兜底
        """
        queries = []
        domain_kw = "camouflaged object detection"

        # 策略1：从 decoder_type 提取技术关键词（最具区分性，直接出现在论文标题里）
        # 例：decoder_type="扩散去噪解码器 DDPM 10步" → 提取 diffusion, DDPM
        decoder_tech = []
        if hint.decoder_type:
            decoder_lower = hint.decoder_type.lower()
            for kw in ["diffusion", "ddpm", "ddim", "mamba", "transformer",
                       "sam", "segment anything", "unet", "u-net"]:
                if kw in decoder_lower:
                    decoder_tech.append(kw)
        if decoder_tech:
            queries.append(decoder_tech[0] + " " + domain_kw)
            if hint.backbone:
                bb_clean = re.sub(r'[^a-zA-Z0-9\s\-]', '',
                                  re.split(r'[（(【\u4e00-\u9fff]', hint.backbone)[0]).strip()
                queries.append(bb_clean + " " + decoder_tech[0] + " " + domain_kw)

        # 策略2：backbone + 任务关键词（命中率较高的标准组合）
        if hint.backbone:
            bb_short_raw = re.split(r'[（(【\u4e00-\u9fff]', hint.backbone)[0].strip()
            bb_clean = re.sub(r'[^a-zA-Z0-9\s\-]', '', bb_short_raw).strip()
            bb_short = bb_clean.split()[0] if bb_clean else ""
            if bb_short:
                queries.append(bb_short + " " + domain_kw)
                queries.append(bb_short + " salient object detection")

        # 策略3：从 key_modules 提取 2-5 个大写字母的缩写
        # 只有在 structure_hint 中至少出现2次才认为是核心模块（过滤噪声缩写）
        module_abbrevs = []
        full_text = hint.structure_hint + " " + (hint.data_flow or "")
        for m in hint.key_modules[:6]:
            text = str(m)
            match = re.match(r'^([A-Z]{2,5})\b', text)
            if match:
                abbrev = match.group(1)
                if full_text.upper().count(abbrev) >= 2:
                    module_abbrevs.append(abbrev)
        if module_abbrevs:
            queries.append(" ".join(module_abbrevs[:2]) + " " + domain_kw)

        # 策略4：从 structure_hint / notes 中提取 venue 提示词辅助定位
        venue_hints = re.findall(
            r'\b(CVPR|ICCV|TPAMI|TIP|AAAI|NeurIPS|ECCV)\b',
            hint.structure_hint + " " + (hint.notes or ""),
            re.IGNORECASE
        )
        if venue_hints and hint.backbone:
            bb_raw = re.split(r'[（(【\u4e00-\u9fff]', hint.backbone)[0].strip()
            bb_s = re.sub(r'[^a-zA-Z0-9]', '', bb_raw.split()[0] if bb_raw else "")
            queries.append(venue_hints[0] + " " + bb_s + " " + domain_kw)

        # 策略5：兜底 — 任务+年份+通用技术词
        queries.append(domain_kw + " 2024 2025 transformer")

        # 去重保序，最多5条
        seen: set = set()
        unique: List[str] = []
        for q in queries:
            q = q.strip()
            if q and q not in seen:
                seen.add(q)
                unique.append(q)
        return unique[:5]

    async def _search_one(self, query: str) -> list:
        """执行单次 Semantic Scholar 搜索"""
        params = {
            "query":  query,
            "limit":  8,
            "fields": SEMANTIC_SCHOLAR_FIELDS,
        }
        candidates = []
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(
                    SEMANTIC_SCHOLAR_SEARCH,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"[FigureTracer] API 返回 {resp.status}")
                        return []
                    data = await resp.json()

            for paper in data.get("data", []):
                c = self._parse_paper(paper)
                if c:
                    candidates.append(c)

        except Exception as e:
            logger.warning(f"[FigureTracer] 搜索异常（{query[:30]}）：{e}")

        return candidates

    def _parse_paper(self, paper: dict):
        """将 API 返回的论文数据解析为 PaperCandidate"""
        from shared.models import PaperCandidate

        title = paper.get("title", "")
        if not title:
            return None

        pdf_url = ""
        oa = paper.get("openAccessPdf")
        if oa and oa.get("url"):
            pdf_url = oa["url"]

        arxiv_id = ""
        ext_ids = paper.get("externalIds", {})
        if ext_ids and ext_ids.get("ArXiv"):
            arxiv_id = ext_ids["ArXiv"]

        s2_url = f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}"

        venue_name = ""
        pub_venue = paper.get("publicationVenue")
        if pub_venue:
            venue_name = pub_venue.get("name", "")
            if not venue_name:
                alts = pub_venue.get("alternateNames", [])
                if alts:
                    venue_name = alts[0]
        if not venue_name:
            venue_name = paper.get("venue", "")

        return PaperCandidate(
            paper_id       = paper.get("paperId", ""),
            title          = title,
            year           = paper.get("year"),
            venue          = venue_name,
            authors        = [a.get("name", "") for a in paper.get("authors", [])[:4]],
            citation_count = paper.get("citationCount", 0) or 0,
            abstract       = (paper.get("abstract") or "")[:500],
            pdf_url        = pdf_url,
            arxiv_id       = arxiv_id,
            s2_url         = s2_url,
        )

    def _deduplicate(self, candidates: list) -> list:
        """按 paper_id 去重，保留引用数最高的"""
        seen: dict = {}
        for c in candidates:
            pid = c.paper_id
            if not pid:
                continue
            if pid not in seen or c.citation_count > seen[pid].citation_count:
                seen[pid] = c
        return list(seen.values())

    def _rank_by_relevance(self, candidates: list, hint) -> list:
        """相关性排序：综合考虑标题匹配度、引用数、年份"""
        keywords = set()
        for m in hint.key_modules[:6]:
            for word in re.findall(r'\b[A-Za-z]{3,}\b', str(m)):
                keywords.add(word.lower())
        if hint.backbone:
            for word in hint.backbone.lower().split():
                keywords.add(word)
        keywords.update({
            "camouflage", "camouflaged", "salient", "detection",
            "diffusion", "transformer", "mamba",
        })

        def score(c) -> float:
            title_words = set(c.title.lower().split())
            overlap    = len(keywords & title_words)
            kw_score   = overlap / max(len(keywords), 1) * 100
            cite_score = math.log10(max(c.citation_count, 1)) * 10
            year_score = max(0, (c.year or 2020) - 2019) * 3
            return kw_score + cite_score + year_score

        return sorted(candidates, key=score, reverse=True)

    def _assess_confidence(self, best, hint) -> str:
        """评估溯源置信度"""
        abbreviations = set(re.findall(r'\b[A-Z]{2,6}\b', hint.structure_hint))
        title_words   = set(best.title.upper().split())
        overlap = len(abbreviations & title_words)

        # 额外检查：decoder_type 中的技术词出现在论文标题或摘要里，提升置信度
        if hint.decoder_type:
            decoder_tech = set(re.findall(
                r'\b(diffusion|ddpm|ddim|mamba|sam|conditional)\b',
                hint.decoder_type.lower()
            ))
            title_lower   = best.title.lower()
            abstract_lower = (best.abstract or "").lower()
            tech_hits = sum(
                1 for t in decoder_tech
                if t in title_lower or t in abstract_lower
            )
            if tech_hits >= 1:
                overlap += 2   # 技术词命中，提升置信度判断

        if overlap >= 2:
            return "high"
        elif overlap >= 1 or best.citation_count > 50:
            return "medium"
        else:
            return "low"

    def _build_summary(self, result) -> str:
        """生成溯源结论的自然语言描述"""
        if not result.best_match:
            return (
                "未找到匹配论文。可能原因：架构图使用了专有缩写，"
                "或该论文尚未被 Semantic Scholar 收录。"
            )

        bm = result.best_match
        conf_map = {"high": "高", "medium": "中等", "low": "低"}
        conf_zh  = conf_map.get(result.confidence, "未知")

        summary = (
            f"最可能的原始论文：《{bm.title}》"
            f"（{bm.year or '年份未知'} / {bm.venue or '期刊未知'}），"
            f"被引 {bm.citation_count} 次，溯源置信度：{conf_zh}。"
        )
        if bm.arxiv_id:
            summary += f" arXiv: {bm.arxiv_id}。"
        if bm.pdf_url:
            summary += " 有开放获取 PDF。"
        summary += f" 共找到 {len(result.candidates)} 篇候选论文。"

        if result.confidence == "low":
            summary += (
                "\n\n> **置信度较低的原因**：架构图中的模块缩写（如 ATCN 等自定义缩写）"
                "通常不出现在其他论文标题里，搜索结果为领域关联度较优的论文但非精确匹配。"
                "建议手动在 [Semantic Scholar](https://www.semanticscholar.org) 或 "
                "[arXiv](https://arxiv.org) 搜索架构图原论文，"
                "确认后可手动填入 code_url 字段。"
            )

        return summary
