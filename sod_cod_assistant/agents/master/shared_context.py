"""
SharedContext 管理器
负责 SharedContext 的创建、更新、持久化和读取。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared.models import SharedContext

logger = logging.getLogger(__name__)


class SharedContextManager:
    """SharedContext 管理器"""

    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)

    def create(self, domain: str, **kwargs) -> SharedContext:
        """创建新的 SharedContext"""
        ctx = SharedContext(domain=domain, **kwargs)
        logger.info(f"[Master] 创建 SharedContext，session_id={ctx.session_id}")
        return ctx

    def save(self, ctx: SharedContext) -> str:
        """
        将 SharedContext 快照保存到文件。

        Returns:
            保存路径
        """
        from config.settings import get_agent_output_dir
        out_dir = Path(get_agent_output_dir(0))
        out_dir.mkdir(parents=True, exist_ok=True)

        path = out_dir / f"master_context_{ctx.session_id}.json"

        # 序列化时排除不可序列化的 Agent 报告对象（保留 summary 字符串）
        data = {
            "session_id":       ctx.session_id,
            "domain":           ctx.domain,
            "created_at":       ctx.created_at.isoformat(),
            "user_method_desc": ctx.user_method_desc,
            "github_url":       ctx.github_url,
            "arch_image_path":  ctx.arch_image_path,
            "visual_image_path":ctx.visual_image_path,
            "plan":             ctx.plan.model_dump() if ctx.plan else None,
            "agent1_done":      ctx.agent1_done,
            "agent2_done":      ctx.agent2_done,
            "agent3_done":      ctx.agent3_done,
            "agent4_done":      ctx.agent4_done,
            "agent1_error":     ctx.agent1_error,
            "agent2_error":     ctx.agent2_error,
            "agent3_error":     ctx.agent3_error,
            "agent4_error":     ctx.agent4_error,
            "agent2_summary":   ctx.agent2_summary,
            "agent3_summary":   ctx.agent3_summary,
            "structure_hint":   ctx.structure_hint,
            "master_narrative": ctx.master_narrative,
            "output_paths":     ctx.output_paths,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.debug(f"[Master] SharedContext 已保存：{path}")
        return str(path)

    def load_latest(self, domain: str) -> Optional[SharedContext]:
        """加载最新的 SharedContext（用于恢复中断的任务）"""
        master_dir = self.cache_dir / "master"
        if not master_dir.exists():
            return None

        files = sorted(master_dir.rglob("master_context_*.json"), reverse=True)
        for f in files:
            try:
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                if data.get("domain") == domain:
                    valid_fields = SharedContext.model_fields.keys()
                    ctx = SharedContext(**{
                        k: v for k, v in data.items()
                        if k in valid_fields
                    })
                    logger.info(f"[Master] 加载历史 SharedContext：{f.name}")
                    return ctx
            except Exception:
                continue
        return None
