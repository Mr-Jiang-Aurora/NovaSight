"""
Agent2 自然语言诊断报告生成器（深度升级版）

升级内容：
1. System Prompt 强约束：禁止套话，每句话必须有数字支撑
2. 传入更丰富的数据上下文（年度进步轨迹、方法间差距、跨数据集比较表格）
3. 生成后质量自检，不合格自动重试（最多 2 次）
4. 报告目标长度：1200-2000 字
"""

import re
import logging

from shared.models import Agent2Report

logger = logging.getLogger(__name__)


# ══ 强约束 System Prompt ══════════════════════════════════════════════

DIAGNOSIS_SYSTEM_PROMPT = """你是一位在 IEEE TPAMI 和 CVPR 发表过多篇论文的 \
COD/SOD 研究方向资深学者，同时担任该领域顶会的审稿人。

你现在为一个面向 COD/SOD 研究者的科研助手系统撰写 SOTA 深度诊断报告。
这份报告是后续代码分析 Agent 的输入上下文，必须足够精确和深入，
使代码分析 Agent 能做出有针对性的改进建议。

━━━ 强制输出规范（违反任何一条即视为不合格）━━━

【规范1】每一个判断都必须有具体数字支撑
  ✗ 不合格："CamoDiffusion 表现优秀"
  ✓ 合格："CamoDiffusion 在 COD10K 的 Sm=0.880，比第二名 ESCNet 高 0.007（0.873），
           但在 CAMO 的 Sm=0.879 反而低于 CFRN（0.881），
           说明 CamoDiffusion 在处理人为伪装场景时存在一定局限"

【规范2】每个研究建议必须包含具体技术路径
  ✗ 不合格："可以考虑改进损失函数"
  ✓ 合格："针对 COD10K Fm 方法间差距 0.148 的现状，建议引入自适应阈值二值化策略，
           在 structure_loss 中加入置信度加权项，参考 ZoomNet（CVPR22）做法"

【规范3】必须进行跨数据集比较
  每个 Top5 方法，必须同时分析其在至少两个数据集上的表现差异，
  并给出可能的原因推断。

【规范4】必须对每个指标的饱和度给出量化判断
  格式："{指标}（{数据集}）：方法间差距={数值}，年均进步≈{数值}/年，
         判定为 {saturating/active/rapid}，含义：{解释}"

【规范5】报告字数不少于1200字，五个章节缺一不可

【规范6】以下套话禁止出现（出现即不合格）
  "取得了显著进展" / "性能高度集中" / "有较大提升空间" /
  "可以考虑" / "值得关注" / "进入精细化竞争阶段" / "表现优秀"

━━━ 报告结构（严格按此顺序输出 Markdown）━━━

## 一、当前领域 SOTA 精确水平
精确列出各数据集各指标的当前 SOTA 数值，
计算5年前基线的累计进步量，分析年度进步率趋势（是否加速/减速）。

## 二、Top5 方法架构差异深度拆解
对每个 Top5 方法进行分析：强弱项（哪个数据集哪个指标相对优/劣）、
与其他 Top 方法的具体差距、推断背后的架构原因。
注意：必须体现跨数据集比较，说明每个方法的「泛化稳定性」。

## 三、指标饱和度量化分析
包含完整的饱和度表格（Markdown 格式），之后对最关键的 2-3 个指标做深度解读。
表格列：指标 | 数据集 | 方法间差距 | 近年进步率 | 状态 | 研究含义

## 四、研究机会与技术路径
2-4 个具体研究方向，每个方向包含：
  - 目标：想在哪个指标/数据集上突破多少
  - 现状：当前 SOTA 数值和方法的局限
  - 技术路径：具体的模块设计或训练策略（要落实到技术细节）
  - 参考工作：现有的相关尝试

## 五、针对性建议
基于以上分析，对选择在该领域开展研究的团队给出最重要的 2-3 条建议，
必须具体说明「应该优先在哪个指标/数据集组合上发力、理由是什么」。

现在请基于提供的数据开始撰写，只输出纯 Markdown 文本，不要输出 JSON 或代码块。"""


# ══ 质量自检配置 ══════════════════════════════════════════════════════

BANNED_PHRASES = [
    "取得了显著进展", "性能高度集中", "有较大提升空间",
    "可以考虑", "值得关注", "进入精细化竞争阶段", "表现优秀",
]

MIN_LENGTH        = 1200
REQUIRED_SECTIONS = ["## 一、", "## 二、", "## 三、", "## 四、", "## 五、"]
MIN_DECIMAL_COUNT = 10   # 至少含有 10 个保留3位小数的数字


def quality_check(text: str) -> tuple[bool, list[str]]:
    """对生成的报告做质量检查，返回 (is_pass, [失败原因])。"""
    failures = []

    if len(text) < MIN_LENGTH:
        failures.append(f"字数不足：{len(text)} < {MIN_LENGTH}")

    missing = [s for s in REQUIRED_SECTIONS if s not in text]
    if missing:
        failures.append(f"缺少章节：{missing}")

    decimal_count = len(re.findall(r'\d+\.\d{3}', text))
    if decimal_count < MIN_DECIMAL_COUNT:
        failures.append(
            f"具体数值不足：找到 {decimal_count} 个3位小数，要求 >= {MIN_DECIMAL_COUNT}"
        )

    found_banned = [p for p in BANNED_PHRASES if p in text]
    if found_banned:
        failures.append(f"包含禁用套话：{found_banned}")

    saturation_kws = ["saturating", "active", "rapid", "饱和", "进步率"]
    if not any(kw in text for kw in saturation_kws):
        failures.append("缺少饱和度分析内容")

    return len(failures) == 0, failures


# ══ 主类 ══════════════════════════════════════════════════════════════

class NarrativeGenerator:
    """Agent2 自然语言诊断报告生成器（双提供商版）"""

    def __init__(self, settings):
        from shared.ai_caller import get_ai_caller, get_active_provider
        self._settings = settings
        self._caller   = get_ai_caller(settings)
        provider       = get_active_provider(settings)

        # 判断当前激活提供商是否有可用 Key
        if provider == "openai":
            self.enabled = bool(getattr(settings, "OPENAI_API_KEY", ""))
        else:
            self.enabled = bool(getattr(settings, "ANTHROPIC_API_KEY", ""))

        if not self.enabled:
            logger.warning(f"[NarrativeGenerator] {provider} API Key 未配置，报告将跳过")

    def generate(
        self,
        report: Agent2Report,
        domain: str,
        user_method_desc: str = "",
        max_retries: int = 2,
    ) -> str:
        """
        生成深度诊断报告，含质量自检和自动重试。

        Args:
            report:           Agent2Report 对象
            domain:           研究领域
            user_method_desc: 用户当前研究方案描述（可选，传入后报告更有针对性）
            max_retries:      质量不过关时的最大重试次数

        Returns:
            中文 Markdown 格式诊断报告
        """
        if not self.enabled:
            return "（自然语言报告未启用，请配置 ANTHROPIC_API_KEY）"

        data_summary = self._build_rich_data_summary(
            report, domain, user_method_desc
        )

        narrative = ""
        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info(f"[Narrative] 质量检查未通过，第 {attempt} 次重试...")

            narrative, fatal = self._call_claude(data_summary, domain, attempt)

            # 致命错误（Key无效/账号耗尽）：直接放弃
            if fatal:
                logger.warning(f"[Narrative] 遇到致命错误，停止重试")
                return narrative

            # 临时错误（503/429）：narrative 是错误提示文字，继续重试
            if narrative.startswith("（") and not fatal:
                from shared.ai_caller import is_temporary_error
                if is_temporary_error(narrative):
                    import time as _time
                    wait = 8 * (attempt + 1)
                    logger.warning(f"[Narrative] 临时 API 错误，等待 {wait}s 后重试")
                    _time.sleep(wait)
                    continue

            passed, failures = quality_check(narrative)
            if passed:
                logger.info(
                    f"[Narrative] 质量检查通过（字数={len(narrative)}，尝试={attempt + 1}次）"
                )
                return narrative
            else:
                logger.warning(f"[Narrative] 质量检查失败：{failures}")

        logger.warning("[Narrative] 达到最大重试次数，返回最终版本（可能质量不足）")
        return narrative + "\n\n> ⚠️ 注意：本报告未能完全满足质量规范，建议人工审查。"

    def _call_claude(self, data_summary: str, domain: str, attempt: int):
        """调用 AI 生成报告。返回 (text, is_fatal_error)。"""
        from shared.ai_caller import get_active_provider
        retry_emphasis = ""
        if attempt > 0:
            retry_emphasis = (
                "\n\n【重试提示】上一次生成的报告质量不达标，请特别注意：\n"
                "1. 每句分析必须有精确的数字（如 0.880，不是「较高」）\n"
                "2. 报告必须达到 1200 字以上\n"
                "3. 必须包含完整的饱和度表格\n"
                "4. 不要使用任何套话\n"
                "请重新撰写，确保满足所有规范。"
            )

        # 刷新 caller（支持运行时切换提供商）
        from shared.ai_caller import get_ai_caller
        caller = get_ai_caller(self._settings)
        user_text = (
            f"请基于以下 {domain} 领域 SOTA 数据，"
            f"撰写深度诊断报告：\n\n"
            f"{data_summary}"
            f"{retry_emphasis}"
        )
        logger.info(f"[Narrative] 使用提供商: {get_active_provider(self._settings)}")
        return caller.chat(
            system=DIAGNOSIS_SYSTEM_PROMPT,
            user_content=user_text,
            max_tokens=8000,
        )

    def _build_rich_data_summary(
        self,
        report: Agent2Report,
        domain: str,
        user_method_desc: str = "",
        top_n: int = 5,
    ) -> str:
        """
        构建传给 Claude 的完整数据摘要。
        包含：各数据集 Top5 四指标表格、饱和度量化数据、
              年度 SOTA 进步轨迹、综合得分排名、用户方案（可选）。
        """
        lines = [
            f"## {domain} 领域 SOTA 完整数据",
            f"分析方法总数：{report.scored_methods} 篇（共 {report.total_methods} 篇）",
            "",
        ]

        # ── 1. 各数据集 Top5 完整四指标表格 ─────────────────────────
        lines.append("### 1. 各数据集 Top5 完整排行（含四指标）")
        lines.append("")

        all_datasets = sorted({r.dataset for r in report.rankings})
        for dataset in all_datasets:
            sm_ranking = next(
                (r for r in report.rankings
                 if r.dataset == dataset and r.metric == "Sm"),
                None,
            )
            if not sm_ranking or not sm_ranking.entries:
                continue

            metric_maps: dict[str, dict[str, float]] = {}
            for metric in ["Em", "Fm", "MAE"]:
                r = next(
                    (r for r in report.rankings
                     if r.dataset == dataset and r.metric == metric),
                    None,
                )
                if r:
                    metric_maps[metric] = {e.paper_id: e.value for e in r.entries}

            lines.append(f"#### {dataset}（Sm ↑ 排行）")
            lines.append("| # | 方法 | 来源 | 年份 | Sm | Em | Fm | MAE |")
            lines.append("|:--:|:--|:--|:--:|:--:|:--:|:--:|:--:|")

            for entry in sm_ranking.entries[:top_n]:
                pid = entry.paper_id
                em  = metric_maps.get("Em",  {}).get(pid)
                fm  = metric_maps.get("Fm",  {}).get(pid)
                mae = metric_maps.get("MAE", {}).get(pid)
                em_s  = f"{em:.3f}"  if em  is not None else "-"
                fm_s  = f"{fm:.3f}"  if fm  is not None else "-"
                mae_s = f"{mae:.4f}" if mae is not None else "-"
                lines.append(
                    f"| {entry.rank} | {entry.title[:38]} | "
                    f"{entry.venue or '-'} | {entry.year or '-'} | "
                    f"**{entry.value:.3f}** | {em_s} | {fm_s} | {mae_s} |"
                )
            lines.append("")

        # ── 2. 饱和度量化完整数据 ─────────────────────────────────────
        lines.append("### 2. 指标饱和度完整数据")
        lines.append("| 指标 | 数据集 | 方法间差距(max-min) | 状态 | 年度进步量(近3年均值) |")
        lines.append("|:--|:--|:--:|:--|:--|")

        for ga in report.gap_analyses:
            for metric, status in ga.saturation.items():
                gap = ga.current_range.get(metric, 0)
                recent_deltas = [
                    ga.yearly_delta[yr][metric]
                    for yr in sorted(ga.yearly_delta.keys())[-3:]
                    if metric in ga.yearly_delta.get(yr, {})
                ]
                avg_delta = (
                    f"≈{sum(recent_deltas) / len(recent_deltas):.4f}/年"
                    if recent_deltas else "数据不足"
                )
                status_zh = {
                    "saturating":        "⚠️ 趋于饱和",
                    "active":            "✅ 正常进步",
                    "rapid":             "🚀 快速进步",
                    "insufficient_data": "❓ 数据不足",
                }.get(status, status)
                lines.append(
                    f"| {metric} | {ga.dataset} | "
                    f"**{gap:.4f}** | {status_zh} | {avg_delta} |"
                )
        lines.append("")

        # ── 3. 年度 SOTA 进步轨迹（COD10K）──────────────────────────
        lines.append("### 3. 年度 SOTA 进步轨迹（COD10K）")
        lines.append("（每年该数据集上各指标的最优值，体现历史进步趋势）")
        lines.append("")

        cod10k_ga = next(
            (ga for ga in report.gap_analyses if ga.dataset == "COD10K"), None
        )
        if cod10k_ga and cod10k_ga.yearly_sota:
            metrics_to_show = ["Sm", "Em", "Fm", "MAE"]
            lines.append("| 年份 | " + " | ".join(metrics_to_show) + " |")
            lines.append("|:--:|" + ":--:|" * len(metrics_to_show))
            for year in sorted(cod10k_ga.yearly_sota.keys()):
                year_data = cod10k_ga.yearly_sota[year]
                vals = []
                for m in metrics_to_show:
                    v = year_data.get(m)
                    if v is not None:
                        vals.append(f"{v:.4f}" if m == "MAE" else f"{v:.3f}")
                    else:
                        vals.append("-")
                lines.append(f"| {year} | " + " | ".join(vals) + " |")
            lines.append("")

        # ── 4. 综合得分完整排名 ───────────────────────────────────────
        lines.append("### 4. 综合得分完整排名（公式：(Sm+Em+Fm)/3 − MAE）")
        lines.append("")

        sorted_profiles = sorted(
            report.profiles, key=lambda p: p.overall_score, reverse=True
        )
        if sorted_profiles:
            lines.append("| # | 方法 | 来源 | 年份 | 综合得分 | 最强项 | 最弱项 |")
            lines.append("|:--:|:--|:--|:--:|:--:|:--:|:--:|")
            for i, p in enumerate(sorted_profiles, 1):
                strongest = (
                    f"{p.strongest_dataset}/{p.strongest_metric}"
                    if p.strongest_dataset else "-"
                )
                weakest = (
                    f"{p.weakest_dataset}/{p.weakest_metric}"
                    if p.weakest_dataset else "-"
                )
                lines.append(
                    f"| {i} | {p.title[:38]} | "
                    f"{p.venue or '-'} | {p.year or '-'} | "
                    f"**{p.overall_score:.4f}** | {strongest} | {weakest} |"
                )
            lines.append("")

        # ── 5. 用户当前研究方案（可选）───────────────────────────────
        if user_method_desc:
            lines += [
                "### 5. 用户当前研究方案描述",
                "",
                user_method_desc,
                "",
                "（请在「五、针对性建议」章节中结合以上方案给出具体建议）",
                "",
            ]
        else:
            lines += [
                "### 5. 用户当前研究方案",
                "",
                "（用户未提供当前方案描述，请在第五章末尾注明"
                "「如需针对具体研究方案的建议，请提供方案描述」）",
                "",
            ]

        return "\n".join(lines)
