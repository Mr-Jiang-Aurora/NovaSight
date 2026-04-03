"""
统一 AI 调用模块 —— 支持 Claude (Anthropic) 和 GPT (OpenAI) 双提供商。

用法：
    from shared.ai_caller import get_ai_caller, AICaller

    caller = get_ai_caller(settings)
    text = caller.chat(
        system="你是专家...",
        user_content="请分析...",
        max_tokens=8000,
    )

    # 带图片（Agent4）
    text = caller.chat(
        system="...",
        user_content="请分析这张图",
        image_data={"base64": "...", "media_type": "image/jpeg"},
        max_tokens=8000,
    )
"""

from __future__ import annotations
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── 运行时可动态切换的活跃提供商（覆盖 .env 设置）──────────────────────
_runtime_provider: Optional[str] = None   # None = 跟随 settings.ACTIVE_AI_PROVIDER


def set_active_provider(provider: str) -> None:
    """动态切换 AI 提供商（不重启服务），provider = 'claude' | 'openai'"""
    global _runtime_provider
    assert provider in ("claude", "openai"), f"未知提供商: {provider}"
    _runtime_provider = provider
    logger.info(f"[AICaller] 切换提供商 → {provider}")


def get_active_provider(settings) -> str:
    """获取当前激活的提供商"""
    return _runtime_provider or getattr(settings, "ACTIVE_AI_PROVIDER", "claude")


# ── 错误类型判断 ────────────────────────────────────────────────────────
#
# 致命错误（不应重试）：
#   - 401 / invalid_api_key / authentication  → Key 无效
#   - "no available accounts"                 → Claude 代理账号耗尽
#   - "blocked"                               → 请求被代理屏蔽
#
# 临时错误（应重试）：
#   - 503 "Service temporarily unavailable"   → 服务短暂过载
#   - 429 "rate_limit"                        → 速率限制，稍后可重试
#
_FATAL_KEYWORDS = [
    "no available accounts",
    "authentication",
    "invalid_api_key",
    "401",
    "blocked",
]

_TEMP_KEYWORDS = [
    "service temporarily unavailable",
    "temporarily unavailable",
    "503",
    "429",
    "rate_limit",
    "too many requests",
    "overloaded",
]


def is_fatal_error(err_str: str) -> bool:
    """不可恢复的致命错误（停止重试）"""
    el = err_str.lower()
    return any(k in el for k in _FATAL_KEYWORDS)


def is_temporary_error(err_str: str) -> bool:
    """临时性错误（可以等待后重试）"""
    el = err_str.lower()
    return any(k in el for k in _TEMP_KEYWORDS)


# ── 主调用类 ────────────────────────────────────────────────────────────

class AICaller:
    """
    统一封装 Anthropic / OpenAI 的文本生成和视觉分析调用。

    - text-only: system + user_content
    - vision:    system + user_content + image_data (base64)
    """

    def __init__(self, settings):
        self.settings = settings
        self.provider = get_active_provider(settings)
        self._claude_client = None
        self._openai_client = None
        self._init_clients()

    def _init_clients(self):
        """初始化对应提供商的客户端"""
        try:
            import httpx

            # Anthropic Client
            if getattr(self.settings, "ANTHROPIC_API_KEY", ""):
                import anthropic
                kw = {"api_key": self.settings.ANTHROPIC_API_KEY,
                      "timeout": httpx.Timeout(600.0, connect=30.0)}
                if self.settings.ANTHROPIC_BASE_URL:
                    kw["base_url"] = self.settings.ANTHROPIC_BASE_URL
                self._claude_client = anthropic.Anthropic(**kw)

            # OpenAI Client
            if getattr(self.settings, "OPENAI_API_KEY", ""):
                from openai import OpenAI
                kw2 = {"api_key": self.settings.OPENAI_API_KEY,
                       "timeout": 600.0}
                if self.settings.OPENAI_BASE_URL:
                    # 中转/代理 API 必须带 /v1，否则请求会被 blocked
                    base = self.settings.OPENAI_BASE_URL.rstrip("/")
                    if not base.endswith("/v1"):
                        base = base + "/v1"
                    kw2["base_url"] = base
                self._openai_client = OpenAI(**kw2)

        except Exception as e:
            logger.error(f"[AICaller] 初始化客户端失败：{e}")

    # ── 对外接口：chat() ──────────────────────────────────────────────

    def chat(
        self,
        system: str,
        user_content: str,
        max_tokens: int = 8000,
        image_data: Optional[dict] = None,   # {"base64": "...", "media_type": "..."}
    ) -> tuple[str, bool]:
        """
        调用 AI 生成文本。

        Returns:
            (text, is_fatal)
            - text:     生成的文本（出错时返回错误描述）
            - is_fatal: True = 不可恢复错误（503/429/401），不应重试
        """
        # 动态刷新当前提供商（支持运行时切换）
        self.provider = get_active_provider(self.settings)

        if self.provider == "openai":
            return self._chat_openai(system, user_content, max_tokens, image_data)
        else:
            return self._chat_claude(system, user_content, max_tokens, image_data)

    # ── Claude 调用 ───────────────────────────────────────────────────

    def _chat_claude(self, system, user_content, max_tokens, image_data):
        if not self._claude_client:
            return "（Claude 客户端未初始化，请检查 ANTHROPIC_API_KEY）", True
        try:
            model = (
                getattr(self.settings, "VISION_MODEL", "") or
                self.settings.ANTHROPIC_MODEL
            ) if image_data else self.settings.ANTHROPIC_MODEL

            content: list = []
            if image_data:
                content.append({
                    "type": "image",
                    "source": {
                        "type":       "base64",
                        "media_type": image_data["media_type"],
                        "data":       image_data["base64"],
                    }
                })
            content.append({"type": "text", "text": user_content})

            with self._claude_client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
            ) as stream:
                text = stream.get_final_text().strip()
            return text, False

        except Exception as e:
            err_str = str(e)
            fatal = is_fatal_error(err_str)
            temp  = is_temporary_error(err_str)
            logger.error(f"[AICaller/Claude] 调用失败：{err_str[:200]}")
            if fatal:
                logger.warning("[AICaller/Claude] 致命错误，停止重试（Key无效/账号耗尽）")
            elif temp:
                logger.warning("[AICaller/Claude] 临时错误（503/429），可重试")
            return f"（Claude 调用失败：{err_str[:200]}）", fatal

    # ── OpenAI 调用 ───────────────────────────────────────────────────

    def _chat_openai(self, system, user_content, max_tokens, image_data):
        if not self._openai_client:
            return "（OpenAI 客户端未初始化，请检查 OPENAI_API_KEY）", True
        try:
            model = self.settings.OPENAI_MODEL

            # 构造 messages
            messages = [{"role": "system", "content": system}]

            if image_data:
                b64 = image_data["base64"]
                mime = image_data["media_type"]
                user_msg_content = [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                    {"type": "text", "text": user_content},
                ]
                messages.append({"role": "user", "content": user_msg_content})
            else:
                messages.append({"role": "user", "content": user_content})

            # 使用 streaming
            full_text = []
            stream = self._openai_client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    full_text.append(delta.content)

            return "".join(full_text).strip(), False

        except Exception as e:
            err_str = str(e)
            fatal = is_fatal_error(err_str)
            temp  = is_temporary_error(err_str)
            logger.error(f"[AICaller/OpenAI] 调用失败：{err_str[:200]}")
            if fatal:
                logger.warning("[AICaller/OpenAI] 致命错误，停止重试（Key无效/账号耗尽）")
            elif temp:
                logger.warning(f"[AICaller/OpenAI] 临时错误（503/429），可重试")
            return f"（OpenAI 调用失败：{err_str[:200]}）", fatal


# ── 便捷工厂函数 ────────────────────────────────────────────────────────

def get_ai_caller(settings) -> AICaller:
    """
    根据当前配置创建 AICaller 实例。
    每次调用都会尊重 _runtime_provider 的最新值。
    """
    return AICaller(settings)


# ── 速度测试（轻量 ping）────────────────────────────────────────────────

def test_provider(provider: str, settings) -> dict:
    """
    测试指定提供商的连通性。
    返回 {"ok": bool, "latency_ms": int, "model": str, "error": str}
    """
    start = time.time()
    try:
        import httpx
        if provider == "claude":
            if not getattr(settings, "ANTHROPIC_API_KEY", ""):
                return {"ok": False, "latency_ms": 0, "model": "", "error": "未配置 ANTHROPIC_API_KEY"}
            import anthropic
            kw = {"api_key": settings.ANTHROPIC_API_KEY,
                  "timeout": httpx.Timeout(30.0, connect=15.0)}
            if settings.ANTHROPIC_BASE_URL:
                kw["base_url"] = settings.ANTHROPIC_BASE_URL
            client = anthropic.Anthropic(**kw)
            client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=5,
                messages=[{"role": "user", "content": "hi"}],
            )
            ms = int((time.time() - start) * 1000)
            return {"ok": True, "latency_ms": ms, "model": settings.ANTHROPIC_MODEL, "error": ""}

        elif provider == "openai":
            if not getattr(settings, "OPENAI_API_KEY", ""):
                return {"ok": False, "latency_ms": 0, "model": "", "error": "未配置 OPENAI_API_KEY"}
            from openai import OpenAI
            kw2 = {"api_key": settings.OPENAI_API_KEY, "timeout": 30.0}
            if settings.OPENAI_BASE_URL:
                base = settings.OPENAI_BASE_URL.rstrip("/")
                kw2["base_url"] = base if base.endswith("/v1") else base + "/v1"
            client = OpenAI(**kw2)
            client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                max_tokens=5,
                messages=[{"role": "user", "content": "hi"}],
            )
            ms = int((time.time() - start) * 1000)
            return {"ok": True, "latency_ms": ms, "model": settings.OPENAI_MODEL, "error": ""}

        else:
            return {"ok": False, "latency_ms": 0, "model": "", "error": f"未知提供商: {provider}"}

    except Exception as e:
        ms = int((time.time() - start) * 1000)
        return {"ok": False, "latency_ms": ms, "model": "", "error": str(e)[:200]}
