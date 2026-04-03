"""
综合报告生成器 —— 分段生成版
将完整报告分为 6 个独立章节分别调用 Claude，
每章 4000 token，总计可达 20000-24000 token 的深度报告。
"""

import logging
from typing import List

from shared.models import SharedContext

logger = logging.getLogger(__name__)


# ══ 各章节独立 System Prompt ════════════════════════════════════════

_EXPERT_PREFIX = """你是一位 COD/SOD 研究领域的资深导师，
在 TPAMI/CVPR/ICCV 有多篇发表，同时深度参与代码工程实践。
你正在为一位本科生研究者撰写深度诊断报告的某一章节。

强制要求：
- 每个判断必须有具体数字支撑
- 每条建议必须可立即执行（有文件路径/代码提示）
- 禁止套话（"有提升空间"/"可以考虑"/"值得关注"）
- 本章节字数不少于 800 字
"""

SECTION_PROMPTS = {
    "section1_sota": _EXPERT_PREFIX + """
你负责撰写报告的【第一章：SOTA 现状精确定标】。

内容要求（必须全部覆盖）：
1. 当前三大数据集（COD10K/CAMO/NC4K）的 SOTA 精确数值表格
2. 近5年进步轨迹（2020→2025 各年最优 Sm/Em/Fm/MAE，配表格）
3. 各指标的年均进步率和饱和度判断（配具体数值）
4. 当前方法间的性能差距（最强vs最弱，每个指标的极差）
5. 小结：哪些指标还有大空间，哪些已经趋于饱和

格式：使用 Markdown 表格、标题、加粗。章节标题固定为：## 一、SOTA 现状精确定标
""",

    "section2_methods": _EXPERT_PREFIX + """
你负责撰写报告的【第二章：Top 方法深度对比分析】。

内容要求（必须全部覆盖）：
1. Top5 方法逐一分析：
   - 架构特点（用一句话描述核心设计）
   - 在三个数据集上的表现差异（是否有数据集特异性）
   - 强项指标和弱项指标（对比榜单找出）
   - 与其他 Top 方法的具体差距数值
2. 跨数据集泛化能力排名（哪个方法最稳定，哪个最不稳定）
3. 失败模式分析：从指标特征推断每个方法的架构短板
4. 方法演进趋势：从 2020 年到 2025 年，主流架构发生了哪些变化

格式：每个方法用三级标题，配详细数字表格。章节标题：## 二、Top 方法深度对比分析
""",

    "section3_arch": _EXPERT_PREFIX + """
你负责撰写报告的【第三章：用户代码架构诊断】。

注意：如果没有提供代码分析数据，请在章节开头说明「本次未提供代码，以下基于
SOTA 方法特征给出通用架构建议」，然后继续按要求写满 800 字。

内容要求（必须全部覆盖）：
1. 用户当前架构的完整描述（来自 Agent3 分析，或基于用户描述推断）
2. 架构的强项：在哪些设计上有优势
3. 架构的弱项：对比 SOTA，缺少哪些关键组件
4. 逐文件的具体问题（有代码时：文件名:行号:问题描述）
5. 损失函数分析：当前损失组合的优缺点，对比 SOTA 方法的损失设计
6. 训练配置分析：batch size/lr/optimizer/input size 是否合理
7. 与 CamoDiffusion（当前 SOTA）的架构级对比

格式：有代码数据时精确到行号；无代码时给出通用最佳实践。
章节标题：## 三、用户代码架构诊断
""",

    "section4_gap": _EXPERT_PREFIX + """
你负责撰写报告的【第四章：与 SOTA 差距量化分析】。

内容要求（必须全部覆盖）：
1. 预计当前方案的性能范围（三个数据集各指标的估算值和置信区间）
2. 与当前 SOTA 的差距分解：
   - 架构差距贡献（占总差距的比例估算）
   - 损失函数差距贡献
   - 训练策略差距贡献
   - 数据/增强策略差距贡献
3. 历史先例分析：同类改进在历史上带来过多少提升（有数据支持）
4. 「低垂果实」识别：哪些改动成本低但收益大（投入产出比分析）
5. 「瓶颈分析」：什么改动做了也不会有明显提升（避免浪费时间）

格式：用表格展示差距分解，用数字量化每项贡献。
章节标题：## 四、与 SOTA 差距量化分析
""",

    "section5_roadmap": _EXPERT_PREFIX + """
你负责撰写报告的【第五章：优先改进路线图】。

这是报告最核心的章节，必须写得极其详细可操作。

内容要求（必须全部覆盖）：
对每条改进建议，必须包含以下 7 个要素：

【优先级】高/中/低
【目标指标】提升哪个数据集的哪个指标，从多少到多少
【技术方案】具体的改动内容（精确到模块名/函数名/代码位置）
【实现步骤】分步骤描述如何实现（至少 3 步）
【参考实现】参考哪篇论文的哪种做法（含年份和来源）
【预计收益】量化的指标提升估计（如 COD10K Sm +0.015~0.025）
【实现成本】时间估算（如 2小时/半天/1天）

建议数量：至少 6 条，按优先级排序（高优先级在前）。

重要：必须完整写完所有建议（至少6条），每条都有完整的7个要素。
如果前几条写得太长，后面的条目可以适当精简，但绝对不能出现空标题。
每条建议的标题格式：### 5.X 建议名称（X为序号）
最后一条写完后，在末尾加上：
---
*本章共列出 [N] 条优先改进建议，按预期收益从高到低排序。*

格式：每条用三级标题，内容详尽，不少于 150 字/条。
章节标题：## 五、优先改进路线图
""",

    "section6_checklist": _EXPERT_PREFIX + """
你负责撰写报告的【第六章：行动清单与里程碑规划】。

内容要求（必须全部覆盖）：

**A. 近期行动清单（CheckList 格式，未来 2 周内可完成）**
- [ ] 今天（预计时间）：具体任务描述
- [ ] 明天：...
- [ ] 本周（Day 3-5）：...
- [ ] 下周（Day 6-10）：...
至少 10 条，每条明确到具体文件/代码/实验。

**B. 里程碑规划（未来 1-3 个月）**
里程碑1（1个月内）：目标性能 + 具体实现的改动 + 验证方式
里程碑2（2个月内）：目标性能 + 需要实现的新模块 + 对比实验设计
里程碑3（3个月内）：投稿目标 + 需要补充的实验 + 论文写作计划

**C. 风险评估与应对**
列出 3 个可能遇到的困难，每个给出应对策略。

**D. 资源清单**
需要的参考代码仓库（含链接）、数据集下载链接、关键论文列表。

格式：全部用 Markdown CheckList 和表格。
章节标题：## 六、行动清单与里程碑规划
""",
}


class SynthesisGenerator:
    """综合报告生成器（双提供商版）"""

    def __init__(self, settings):
        from shared.ai_caller import get_ai_caller, get_active_provider
        self._settings = settings
        self._caller   = get_ai_caller(settings)
        provider       = get_active_provider(settings)

        if provider == "openai":
            self.enabled = bool(getattr(settings, "OPENAI_API_KEY", ""))
        else:
            self.enabled = bool(getattr(settings, "ANTHROPIC_API_KEY", ""))

        if not self.enabled:
            logger.warning(f"[SynthesisGenerator] {provider} API Key 未配置")

    async def generate_segmented(self, ctx: SharedContext) -> List[str]:
        """
        分段生成综合报告。
        每章独立调用 Claude，max_tokens=4000。
        返回 6 个章节的文字列表。
        """
        if not self.enabled:
            return [self._fallback(ctx)]

        data_summary = self._build_full_data_summary(ctx)
        section_keys = [
            "section1_sota",
            "section2_methods",
            "section3_arch",
            "section4_gap",
            "section5_roadmap",
            "section6_checklist",
        ]
        section_names = [
            "SOTA现状", "方法对比", "架构诊断",
            "差距分析", "改进路线图", "行动清单",
        ]

        parts = []
        for key, name in zip(section_keys, section_names):
            logger.info(f"[Synthesis] 生成章节：{name}...")
            content = self._generate_section(key, data_summary, ctx)
            parts.append(content)
            logger.info(f"[Synthesis] {name} 完成，字数={len(content)}")

        total_chars = sum(len(p) for p in parts)
        logger.info(f"[Synthesis] 全部章节完成，总字数={total_chars}")
        return parts

    def _generate_section(
        self,
        section_key:  str,
        data_summary: str,
        ctx:          SharedContext,
    ) -> str:
        """生成单个章节"""
        system_prompt = SECTION_PROMPTS.get(section_key, _EXPERT_PREFIX)
        user_content  = (
            f"研究领域：{ctx.domain}\n"
            f"用户当前方案：{ctx.user_method_desc or '（未提供）'}\n\n"
            f"以下是所有 Agent 的分析数据，请基于此撰写本章节：\n\n"
            f"{data_summary}\n\n"
            f"请开始撰写本章节，要求详尽，字数不少于 800 字。"
        )
        try:
            import time as _time
            from shared.ai_caller import get_ai_caller, get_active_provider, is_temporary_error
            caller = get_ai_caller(self._settings)
            logger.info(f"[Synthesis] {section_key} 使用提供商: {get_active_provider(self._settings)}")

            text, is_fatal = "", False
            for attempt in range(3):   # 最多重试 3 次（针对临时 503/429）
                if attempt > 0:
                    wait = 10 * attempt  # 10s, 20s
                    logger.info(f"[Synthesis] {section_key} 第 {attempt+1} 次重试，等待 {wait}s...")
                    _time.sleep(wait)

                text, is_fatal = caller.chat(
                    system=system_prompt,
                    user_content=user_content,
                    max_tokens=10000,
                )

                if is_fatal:
                    logger.warning(f"[Synthesis] {section_key} 致命错误，不重试")
                    break
                if text and not text.startswith("（"):
                    break  # 成功拿到内容
                # 判断是否是临时错误，决定是否重试
                if not is_temporary_error(text):
                    logger.warning(f"[Synthesis] {section_key} 非临时错误，停止重试")
                    break
                logger.warning(f"[Synthesis] {section_key} 临时错误，准备重试")

            if is_fatal or not text or text.startswith("（"):
                logger.warning(f"[Synthesis] {section_key} AI 调用失败，跳过本章节")
                return f"## （{section_key} 生成失败：AI 服务暂不可用，请稍后重试综合报告）"

            stop_reason = "end_turn"  # streaming 模式不返回 stop_reason，默认正常

            # 检测截断：stop_reason=max_tokens 时在末尾追加提示
            if stop_reason == "max_tokens":
                logger.warning(
                    f"[Synthesis] {section_key} 触及 max_tokens，内容可能不完整"
                )
                # 找到最后一个完整的段落结尾（两个换行符）
                last_para = text.rfind("\n\n")
                if last_para > len(text) // 2:
                    text = text[:last_para].rstrip()
                text += "\n\n---\n*（本章因篇幅限制在此截止，核心改进方向已在前述条目中完整呈现）*"

            # 检查各种截断模式
            import re

            # 模式1：### X.Y 标题后直接跟 ## 下一章（内容为空）
            empty_after_next = re.search(
                r'(###\s+\d+\.\d+[^\n]*)\n\s{0,5}(?=##)', text
            )
            # 模式2：文本末尾是一个 ### X.Y 标题（可能有1-2行内容但不完整）
            # 判断标准：最后一个 ### X.Y 的内容少于 50 字符
            last_section_match = None
            for m in re.finditer(r'###\s+\d+\.\d+[^\n]*', text):
                last_section_match = m
            if last_section_match:
                content_after_last = text[last_section_match.end():].strip()
                if len(content_after_last) < 50:
                    # 最后一个子章节内容太少，视为截断
                    text = text[:last_section_match.start()].rstrip()
                    text += "\n\n---\n*（本章因篇幅限制在此截止，核心改进方向已在前述条目中完整呈现）*"
                    logger.warning(
                        f"[Synthesis] {section_key} 检测到末尾章节内容过短（截断），已补全收尾"
                    )
            elif empty_after_next:
                text = text[:empty_after_next.start()].rstrip()
                text += "\n\n---\n*（本章因篇幅限制在此截止，核心改进方向已在前述条目中完整呈现）*"
                logger.warning(
                    f"[Synthesis] {section_key} 检测到空标题截断，已补全收尾"
                )

            return text
        except Exception as e:
            logger.error(f"[Synthesis] 章节 {section_key} 生成失败：{e}")
            return f"## （{section_key} 生成失败：{e}）"

    def _build_full_data_summary(self, ctx: SharedContext) -> str:
        """构建传给 Claude 的完整数据摘要（所有 Agent 数据）"""
        parts = []

        # ── Agent1 数据 ──────────────────────────────────────────
        if ctx.leaderboard:
            lb     = ctx.leaderboard
            scored = [p for p in lb.papers if p.scores]
            parts.append(
                f"## Agent1 数据（{lb.total_papers}篇论文，{len(scored)}篇有分数）"
            )
            for p in sorted(scored, key=lambda x: x.year or 0, reverse=True)[:10]:
                score_str = ""
                if p.scores and "COD10K" in p.scores:
                    s = p.scores["COD10K"]
                    def _f3(v): return f"{v:.3f}" if v is not None else "?"
                    def _f4(v): return f"{v:.4f}" if v is not None else "?"
                    score_str = (
                        f"COD10K[Sm={_f3(s.Sm)},Em={_f3(s.Em)},"
                        f"Fm={_f3(s.Fm)},MAE={_f4(s.MAE)}]"
                    )
                parts.append(
                    f"  - {p.title[:45]} [{p.venue or '-'},{p.year or '-'}] {score_str}"
                )

        # ── Agent2 数据 ──────────────────────────────────────────
        if ctx.agent2_summary:
            parts.append(f"\n## Agent2 指标诊断摘要\n{ctx.agent2_summary}")

        if ctx.agent2_report:
            r = ctx.agent2_report
            if hasattr(r, "rankings") and r.rankings:
                for ranking in r.rankings:
                    if ranking.dataset == "COD10K" and ranking.metric == "Sm":
                        parts.append("\n### COD10K Sm 完整排行：")
                        parts.append("| # | 方法 | 来源 | 年份 | Sm |")
                        parts.append("|:--:|:--|:--|:--:|:--:|")
                        for e in ranking.entries[:10]:
                            val_str = f"{e.value:.3f}" if e.value is not None else "?"
                            parts.append(
                                f"| {e.rank} | {e.title[:38]} | "
                                f"{e.venue or '-'} | {e.year or '-'} | "
                                f"**{val_str}** |"
                            )
            if hasattr(r, "gap_analyses") and r.gap_analyses:
                for ga in r.gap_analyses:
                    if ga.dataset == "COD10K":
                        parts.append("\n### COD10K 饱和度（方法间差距）：")
                        for metric, gap in ga.current_range.items():
                            sat = ga.saturation.get(metric, "?")
                            gap_str = f"{gap:.4f}" if gap is not None else "?"
                            parts.append(f"  {metric}: 差距={gap_str}, 状态={sat}")
                        if ga.yearly_sota:
                            parts.append("\n### COD10K 年度 SOTA 进步：")
                            parts.append("| 年份 | Sm | Em | Fm | MAE |")
                            parts.append("|:--:|:--:|:--:|:--:|:--:|")
                            for yr in sorted(ga.yearly_sota.keys()):
                                yd = ga.yearly_sota[yr]
                                parts.append(
                                    f"| {yr} | {yd.get('Sm','?')} | "
                                    f"{yd.get('Em','?')} | "
                                    f"{yd.get('Fm','?')} | "
                                    f"{yd.get('MAE','?')} |"
                                )
            if hasattr(r, "narrative") and r.narrative:
                parts.append(f"\n### Agent2 叙述报告：\n{r.narrative[:2000]}")

        # ── Agent3 数据 ──────────────────────────────────────────
        if ctx.agent3_report:
            a = getattr(ctx.agent3_report, "analysis", None)
            if a:
                parts.append("\n## Agent3 代码架构分析")
                if getattr(a, "arch_summary", ""):
                    parts.append(f"架构摘要：{a.arch_summary}")
                if getattr(a, "components", []):
                    parts.append("识别组件：" + "；".join(
                        f"{c.component_type}={c.name}"
                        for c in a.components[:8]
                    ))
                if getattr(a, "losses", []):
                    parts.append("损失函数：" + "；".join(
                        f"{l.loss_name}(w={l.weight})"
                        for l in a.losses
                    ))
                if getattr(a, "train_config", None):
                    tc = a.train_config
                    parts.append(
                        f"训练配置：bs={tc.batch_size},lr={tc.learning_rate},"
                        f"opt={tc.optimizer},input={tc.input_size}"
                    )
                if getattr(a, "suggestions", []):
                    parts.append("改进建议：")
                    for s in a.suggestions:
                        parts.append(
                            f"  [{s.priority}][{s.category}] {s.suggestion[:200]}"
                        )
                if getattr(a, "sota_gap_summary", ""):
                    parts.append(f"SOTA差距：{a.sota_gap_summary}")

        # ── Agent4 数据 ──────────────────────────────────────────
        if ctx.agent4_report:
            r4 = ctx.agent4_report
            arch_hint = getattr(r4, "arch_hint", None)
            if arch_hint and getattr(arch_hint, "structure_hint", ""):
                parts.append("\n## Agent4 架构图解析")
                parts.append(f"Structure Hint：{arch_hint.structure_hint}")
                if getattr(arch_hint, "key_modules", []):
                    parts.append("关键模块：")
                    for m in arch_hint.key_modules[:5]:
                        parts.append(f"  - {str(m)[:150]}")
            visual = getattr(r4, "visual", None)
            if visual and getattr(visual, "key_findings", []):
                parts.append("\n## Agent4 可视化分析")
                for finding in visual.key_findings[:5]:
                    parts.append(f"  - {finding}")

        return "\n".join(parts)

    def _fallback(self, ctx: SharedContext) -> str:
        """API 不可用时的降级报告"""
        lines = [
            f"# {ctx.domain} 综合报告（降级版，API 不可用）",
            "",
            "Agent 状态：",
            f"- Agent1: {'完成' if ctx.agent1_done else '失败'}",
            f"- Agent2: {'完成' if ctx.agent2_done else '失败'}",
            f"- Agent3: {'完成' if ctx.agent3_done else '失败'}",
            f"- Agent4: {'完成' if ctx.agent4_done else '失败'}",
            "",
        ]
        if ctx.agent2_summary:
            lines += ["## SOTA 摘要", ctx.agent2_summary]
        if ctx.agent3_summary:
            lines += ["## 代码摘要", ctx.agent3_summary]
        return "\n".join(lines)
