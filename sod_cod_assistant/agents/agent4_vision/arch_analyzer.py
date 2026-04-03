"""
模式1：架构图深度解析器（升级版）
调用 Claude Vision API，对网络架构图进行六维度深度分析。

升级内容：
1. max_tokens 1500 → 4000
2. System Prompt 强制六维度分析：功能/设计动机/数据流/架构对比/代码映射/局限性
3. key_modules 从字符串列表 → 结构化对象列表
4. 质量自检 + 自动重试（最多 2 次）
"""

import json
import re
import logging
from typing import Optional
import anthropic
import httpx

from shared.models import ArchHint

logger = logging.getLogger(__name__)


# ══ 深度分析 System Prompt ══════════════════════════════════════════

ARCH_ANALYSIS_SYSTEM = """你是一位在 CVPR/ICCV/TPAMI 发表过多篇 COD/SOD 论文的资深研究员，
深度熟悉扩散模型、Transformer、CNN 等架构在视觉任务中的应用。

你的任务是对用户提交的神经网络架构图进行深度分析。
这份分析将作为代码分析 Agent（Agent3）的输入上下文，
必须足够深入精确，使 Agent3 能精准定位创新模块并给出针对性改进建议。

━━━ 强制分析规范（违反任何一条即不合格，系统将自动重试）━━━

【规范1】每个识别到的模块必须分析功能和设计动机，不能只写名字
  ✗ 不合格："ATCN 模块"
  ✓ 合格："ATCN：以时间步 t 为调制信号，将 PVT 提取的 F1-F4 多尺度特征
            转化为时间步自适应的条件特征；设计动机：扩散模型的去噪网络
            在不同时间步需要不同程度的语义引导，固定条件特征会导致
            早期步骤（粗结构恢复）和晚期步骤（细节精化）使用相同强度的
            语义信息，ATCN 通过时间步调制解决了这个问题"

【规范2】数据流必须区分训练路径和推理路径
  训练路径：x_0 如何加噪 → 条件特征如何注入 → GT 如何监督
  推理路径：从 x_T 开始 → 每步去噪逻辑 → 迭代步数 → 最终输出

【规范3】必须进行架构对比分析（与至少 2 种标准 COD/SOD 网络比较）
  - 与 U-Net 系列的本质区别
  - 与标准 Transformer 分割网络的区别
  - 该设计的优势（要有架构依据）和代价（速度/内存/训练难度）

【规范4】每个创新模块必须推断代码映射
  - 推断的文件路径（如 models/atcn.py）
  - 推断的主要类名（如 class ATCN）
  - 推断的关键方法（如 def forward(self, features, t)）

【规范5】必须分析局限性（从架构角度，每条有依据）
  例：扩散模型的多步推理 → 推理速度慢；
      条件网络参数量 → 训练数据需求高

【规范6】structure_hint 字段必须 > 150字，包含所有关键模块的一句话功能描述

━━━ 输出格式（严格 JSON，不加任何其他文字）━━━

{
  "backbone": "精确名称含变体（如 PVT-v2-b2，不只是 PVT）",
  "decoder_type": "详细描述（类型+特点+步数，如 扩散去噪解码器，10步DDIM采样，U-Net结构）",

  "key_modules": [
    {
      "name": "模块名称（缩写 → 全称）",
      "function": "功能描述（2-3句，说清楚做什么、输入输出是什么）",
      "design_motivation": "设计动机（为什么需要这个模块，解决了什么标准做法解决不了的问题）",
      "input_output": "输入输出格式（如：输入 F1-F4[B,C,H,W] + 时间步t，输出 Z1-Z4 条件特征）",
      "code_hint": "推断的代码位置（文件路径:类名:关键方法）"
    }
  ],

  "data_flow": {
    "training": "训练路径完整描述（从输入图像和GT到损失函数的完整流程）",
    "inference": "推理路径完整描述（从 x_T 到最终预测的迭代过程，含步数）",
    "key_connections": "关键的跳跃连接和残差连接描述"
  },

  "arch_comparison": {
    "vs_unet": "与 U-Net 系列的本质区别（2-3句，要有实质内容）",
    "vs_transformer_seg": "与标准 Transformer 分割网络（如 Segmenter、MaskFormer）的区别",
    "advantages": [
      "优势1（有架构依据的具体优势）",
      "优势2"
    ],
    "limitations": [
      "局限1（有架构依据，如：多步采样导致推理时间是单步方法的N倍）",
      "局限2"
    ]
  },

  "file_hints": [
    {
      "file": "推断的文件路径（如 models/atcn.py）",
      "contains": "该文件的功能描述",
      "key_class": "推断的主要类名",
      "key_methods": ["forward", "其他关键方法"]
    }
  ],

  "structure_hint": "给 Agent3 的完整结构描述（150字以上，包含backbone名称、所有关键模块的一句话功能、数据流概述、训练/推理差异、文件结构推断）",

  "confidence": "high/medium/low（基于图片清晰度和信息完整度）",
  "notes": "额外观察（颜色标注的含义、图中数学符号的解读、特殊设计细节等）"
}"""


# ══ 质量自检 ════════════════════════════════════════════════════════

QUALITY_CHECKS = [
    ("key_modules 每个含 function 字段",
     lambda d: all(
         isinstance(m, dict) and len(m.get("function", "")) > 20
         for m in d.get("key_modules", [{}])
     )),
    ("key_modules 每个含 design_motivation",
     lambda d: all(
         isinstance(m, dict) and len(m.get("design_motivation", "")) > 10
         for m in d.get("key_modules", [{}])
     )),
    ("data_flow 包含 training 和 inference",
     lambda d: all(
         k in d.get("data_flow", {}) and len(d["data_flow"].get(k, "")) > 20
         for k in ["training", "inference"]
     )),
    ("arch_comparison 包含 limitations",
     lambda d: bool(d.get("arch_comparison", {}).get("limitations"))),
    ("file_hints 每条含 key_class",
     lambda d: all(
         isinstance(f, dict) and f.get("key_class")
         for f in d.get("file_hints", [{}])
     )),
    ("structure_hint 长度 > 100字",
     lambda d: len(d.get("structure_hint", "")) > 100),
]


def quality_check(data: dict) -> tuple[bool, list[str]]:
    failures = []
    for desc, check_fn in QUALITY_CHECKS:
        try:
            if not check_fn(data):
                failures.append(f"未通过：{desc}")
        except Exception as e:
            failures.append(f"检查异常（{desc}）：{e}")
    return len(failures) == 0, failures


# ══ 主类 ════════════════════════════════════════════════════════════

class ArchAnalyzer:
    """架构图深度解析器（双提供商版）"""

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
            logger.warning(f"[ArchAnalyzer] {provider} API Key 未配置，架构图解析将跳过")

    def analyze(
        self,
        image_data:  dict,
        user_hint:   str = "",
        max_retries: int = 2,
    ) -> ArchHint:
        hint = ArchHint(
            image_path=image_data.get("path", ""),
            image_desc=user_hint or image_data.get("path", ""),
        )

        if not self.enabled:
            hint.notes      = "Vision API 未启用"
            hint.confidence = "low"
            return hint

        data = None
        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info(f"[ArchAnalyzer] 质量不足，第 {attempt} 次重试")

            raw, is_fatal = self._call_claude(image_data, user_hint, attempt)
            if is_fatal:
                logger.warning("[ArchAnalyzer] 遇到不可恢复 API 错误，停止重试")
                hint.notes = raw
                hint.confidence = "low"
                break

            data = self._parse_json(raw)

            if data is None:
                continue

            passed, failures = quality_check(data)
            if passed:
                logger.info(f"[ArchAnalyzer] 质量检查通过（尝试 {attempt + 1} 次）")
                self._update_hint(hint, data)
                break   # 不提前 return，继续执行 TASK1/3
            else:
                logger.warning(f"[ArchAnalyzer] 质量不足：{failures}")

        # 最终仍不过关，尽力更新（quality_check 未通过时）
        if data and not hint.key_modules:
            self._update_hint(hint, data)
            logger.warning("[ArchAnalyzer] 达到最大重试次数，使用最终版本")

        # TASK1：Figure 溯源（在独立线程+事件循环中运行，避免与外层 async 冲突）
        if hint.confidence in ("high", "medium"):
            try:
                import threading
                import asyncio as _asyncio
                from agents.agent4_vision.figure_tracer import FigureTracer

                api_key = getattr(self, "_semantic_scholar_api_key", "")
                tracer  = FigureTracer(api_key=api_key)
                _result: list = [None]

                def _run_in_thread():
                    _loop = _asyncio.new_event_loop()
                    _asyncio.set_event_loop(_loop)
                    try:
                        _result[0] = _loop.run_until_complete(tracer.trace(hint))
                    finally:
                        _loop.close()

                t = threading.Thread(target=_run_in_thread, daemon=True)
                t.start()
                t.join(timeout=30)   # 最多等待 30 秒

                trace_result = _result[0]
                if trace_result:
                    hint.trace_result = trace_result
                    if trace_result.best_match:
                        logger.info(
                            f"[FigureTracer] 溯源完成：{trace_result.best_match.title[:50]}"
                            f"（置信度={trace_result.confidence}）"
                        )
                    else:
                        logger.info("[FigureTracer] 溯源完成，未找到强匹配论文")
                else:
                    logger.warning("[FigureTracer] 溯源超时或无结果")
            except Exception as e:
                logger.warning(f"[FigureTracer] 溯源失败（不影响主流程）：{e}")

        # TASK3：学术创新性评估
        if hint.confidence in ("high", "medium") and image_data:
            sota_context = getattr(self, "_sota_context", "")
            hint.innovation_evaluation = self.evaluate_innovation(
                image_data   = image_data,
                arch_hint    = hint,
                sota_context = sota_context,
            )

        return hint

    def _call_claude(
        self, image_data: dict, user_hint: str, attempt: int
    ) -> str:
        retry_note = ""
        if attempt > 0:
            retry_note = (
                "\n\n【重试要求】上次分析质量不够深入，请特别注意：\n"
                "1. key_modules 中每个模块必须包含 function（功能）和 "
                "design_motivation（设计动机）字段，每个字段 > 20 字\n"
                "2. data_flow 必须分别描述 training 和 inference 两条路径\n"
                "3. arch_comparison.limitations 必须有具体内容\n"
                "4. structure_hint 必须超过 150 字\n"
                "请重新仔细读图，确保每个可见模块都有深度分析。"
            )

        prompt = (
            "请对这张神经网络架构图进行深度分析，"
            "必须分析每个模块的功能和设计动机，不能只列名字。"
            + (f"\n用户说明：{user_hint}" if user_hint else "")
            + retry_note
        )

        from shared.ai_caller import get_ai_caller, get_active_provider
        caller = get_ai_caller(self._settings)
        logger.info(f"[ArchAnalyzer] 使用提供商: {get_active_provider(self._settings)}")
        return caller.chat(
            system=ARCH_ANALYSIS_SYSTEM,
            user_content=prompt,
            max_tokens=8000,
            image_data=image_data,
        )

    def _parse_json(self, raw: str) -> Optional[dict]:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # 提取 ```json ... ``` 代码块（贪婪，支持超长 JSON）
        match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 找最外层 { ... }
        start = raw.find('{')
        end   = raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass
        logger.error(f"JSON 解析失败，原始输出：{raw[:200]}")
        return None

    def _update_hint(self, hint: ArchHint, data: dict) -> None:
        hint.backbone       = data.get("backbone")
        hint.decoder_type   = data.get("decoder_type")
        hint.confidence     = data.get("confidence", "medium")
        hint.notes          = data.get("notes", "")
        hint.structure_hint = data.get("structure_hint", "")

        # data_flow：优先用 training 路径，也保存完整对象
        df = data.get("data_flow", {})
        if isinstance(df, dict):
            hint.data_flow = df.get("training", "")
        else:
            hint.data_flow = str(df)

        # key_modules：兼容新格式（对象列表）和旧格式（字符串列表）
        raw_modules = data.get("key_modules", [])
        hint.key_modules = []
        for m in raw_modules:
            if isinstance(m, str):
                hint.key_modules.append(m)
            elif isinstance(m, dict):
                name   = m.get("name", "")
                func   = m.get("function", "")
                motiv  = m.get("design_motivation", "")
                io_d   = m.get("input_output", "")
                code   = m.get("code_hint", "")
                desc   = name
                if func:
                    desc += f"：{func}"
                if motiv:
                    desc += f"【动机：{motiv}】"
                if io_d:
                    desc += f"【IO：{io_d}】"
                if code:
                    desc += f"【代码：{code}】"
                hint.key_modules.append(desc)

        # file_hints：兼容新格式（对象列表）和旧格式（字符串列表）
        raw_hints = data.get("file_hints", [])
        hint.file_hints = []
        for f in raw_hints:
            if isinstance(f, str):
                hint.file_hints.append(f)
            elif isinstance(f, dict):
                fp      = f.get("file", "")
                cont    = f.get("contains", "")
                klass   = f.get("key_class", "")
                methods = f.get("key_methods", [])
                desc    = fp
                if klass:
                    desc += f" → class {klass}"
                if methods:
                    desc += f"（方法：{', '.join(methods[:3])}）"
                if cont:
                    desc += f"：{cont}"
                hint.file_hints.append(desc)

        # 若 structure_hint 为空则从各字段拼接
        if not hint.structure_hint:
            parts = []
            if hint.backbone:
                parts.append(f"Backbone: {hint.backbone}")
            for m in data.get("key_modules", []):
                if isinstance(m, dict):
                    name = m.get("name", "")
                    func = m.get("function", "")[:50]
                    if name:
                        parts.append(f"{name}: {func}")
            if hint.decoder_type:
                parts.append(f"Decoder: {hint.decoder_type}")
            hint.structure_hint = "；".join(parts)

        # 保留原始 Claude 响应供报告写入和后续质量审查
        hint.raw_data = data

    # ── TASK3：学术创新性评估 ─────────────────────────────────────────

    def evaluate_innovation(
        self,
        image_data:   dict,
        arch_hint,
        sota_context: str = "",
    ) -> str:
        """
        学术创新性评估。
        在 analyze() 完成后调用，评估该架构的学术贡献等级。

        Returns:
            创新性评估报告（Markdown 文字）
        """
        if not self.enabled:
            return ""

        system_prompt = """你是一位 TPAMI/CVPR 资深审稿人，
专注 COD/SOD 领域，有判断论文创新性的丰富经验。

你的任务是基于架构图，评估该方法的学术创新性。

━━━ 评估维度（必须全部覆盖）━━━

【维度1】创新等级（必须明确选择其中一项并说明理由）
  - 范式创新（Paradigm）：引入全新的解题思路，如首次将扩散模型用于 COD
  - 架构创新（Architecture）：设计了新颖的网络模块，但整体框架仍是已知范式
  - 改进创新（Incremental）：对已有方法的改进和优化，贡献明确但较为渐进
  - 工程优化（Engineering）：主要是效率改进或实现优化

【维度2】核心贡献点（精确定位）
  该架构与近5年同类方法相比，最本质的区别是什么？
  用一句话说清楚（不超过50字）。

【维度3】与已有工作的差异性
  该架构中有哪些组件是首次出现在 COD/SOD 任务中的？
  有哪些组件是借鉴了其他领域（如扩散模型、LLM）的思路？

【维度4】可能的学术局限性
  从架构角度，这个方法在哪些场景可能表现不好？
  在学术评审中，审稿人最可能提出哪些质疑？

【维度5】对后续研究的启发
  这个方法开辟了哪些新的研究方向？
  如果你要在此基础上做下一篇论文，最有潜力的改进方向是什么？
  - 如果用户提供了当前研究方向，**必须**包含一段「与用户研究的关联分析」：
    指出被分析方法的哪些技术思路可以被用户直接借鉴或设计对比实验。
    这段分析应具体（不超过100字），避免泛泛而谈。

━━━ 输出格式 ━━━
直接输出 Markdown 文本（不是 JSON），包含以上五个维度的标题和内容。
总字数 600-1000 字，每个维度不少于 80 字。"""

        user_content = (
            f"请评估这张架构图展示的方法的学术创新性。\n\n"
            f"架构图解析摘要：{arch_hint.structure_hint}\n\n"
            f"识别到的关键模块：{', '.join(str(m)[:50] for m in arch_hint.key_modules[:5])}\n\n"
            + (f"当前领域 SOTA 参考：\n{sota_context[:500]}\n\n" if sota_context else "")
            + "请基于以上信息和图片进行学术创新性评估。"
        )

        # FIX3：追加强制对比要求（扩散分割方法横向对比 + 用户研究挂钩）
        user_content += (
            "\n\n**特别要求**：\n"
            "1. 维度1（创新等级）判定时，必须与以下同类扩散分割方法进行横向比较：\n"
            "   DiffusionSeg (2022)、SegDiff (2022)、EVPDiff (2023)、DiffuMask (2023)\n"
            "   说明本方法与这些工作的核心区别，而非仅与传统判别式方法比较。\n\n"
            "2. 维度5（后续研究启发）中，如果用户描述了自己的当前研究方案，\n"
            "   请明确指出该方案与被分析方法的技术互补性，\n"
            "   并给出至少一条「基于用户当前方案进行改进」的具体建议。\n"
            + (f"\n用户当前研究方向参考：{sota_context[:300]}\n" if sota_context else "")
        )

        from shared.ai_caller import get_ai_caller, get_active_provider
        caller = get_ai_caller(self._settings)
        logger.info(f"[ArchAnalyzer/Innovation] 使用提供商: {get_active_provider(self._settings)}")
        text, is_fatal = caller.chat(
            system=system_prompt,
            user_content=user_content,
            max_tokens=8000,
            image_data=image_data,
        )
        if is_fatal:
            logger.warning("[ArchAnalyzer] 创新性评估遇到不可恢复错误")
            return ""
        logger.info(f"[ArchAnalyzer] 创新性评估完成，字数={len(text)}")
        return text
