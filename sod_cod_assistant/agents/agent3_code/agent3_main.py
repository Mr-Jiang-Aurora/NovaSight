"""
Agent3 主入口：用户代码架构分析（双输入模式）
"""

import asyncio
import logging
from typing import Optional

from shared.models import (
    Agent3Report, UserCodeAnalysis,
    Agent3InputMode, SOTALeaderboard
)

logger = logging.getLogger(__name__)


class Agent3:
    """用户代码架构分析 Agent（双输入模式）"""

    def __init__(self, settings):
        self.settings = settings

    async def run(
        self,
        github_url:      Optional[str]   = None,
        uploaded_files:  Optional[dict]  = None,   # {filename: bytes}
        zip_bytes:       Optional[bytes] = None,   # zip 包字节
        local_dir:       Optional[str]   = None,   # 本地目录（测试用）
        structure_hint:  str             = "",     # Agent4 传入的结构描述
        agent2_summary:  str             = "",     # 来自 Agent2 的 SOTA 摘要
        domain:          str             = "COD",
        use_claude:      bool            = True,
    ) -> Agent3Report:
        """
        Agent3 主入口，支持双输入模式。

        调用方式示例：
          # 模式A：GitHub 链接
          report = await agent3.run(github_url="https://github.com/xxx/yyy")

          # 模式B：上传文件（Streamlit UI 场景）
          report = await agent3.run(uploaded_files={"net.py": b"...", "loss.py": b"..."})

          # 模式B：本地目录（测试用）
          report = await agent3.run(local_dir="./my_model_code")

          # 两种模式同时使用 + Agent4 增强
          report = await agent3.run(
              github_url="https://github.com/xxx/yyy",
              structure_hint="models/net.py 是主网络；loss.py 是损失函数",
              agent2_summary="当前SOTA CamoDiffusion Sm=0.88..."
          )
        """
        from agents.agent3_code.github_loader    import GitHubLoader
        from agents.agent3_code.upload_loader    import UploadLoader
        from agents.agent3_code.file_selector    import FileSelector
        from agents.agent3_code.arch_extractor   import ArchExtractor
        from agents.agent3_code.loss_extractor   import LossExtractor
        from agents.agent3_code.config_extractor import ConfigExtractor
        from agents.agent3_code.code_interpreter import CodeInterpreter
        from agents.agent3_code.arch_report_writer import ArchReportWriter

        report   = Agent3Report(domain=domain)
        analysis = UserCodeAnalysis(structure_hint=structure_hint)

        # ── 1. 加载代码文件 ───────────────────────────────────────────
        file_contents: dict[str, str] = {}

        if github_url:
            logger.info(f"[Agent3] 模式A：从 GitHub 加载 {github_url}")
            github_token = getattr(self.settings, "GITHUB_TOKEN", "")
            loader = GitHubLoader(github_token)
            gh_files = await loader.load(github_url, structure_hint)
            file_contents.update(gh_files)
            analysis.github_url = github_url
            analysis.input_mode = Agent3InputMode.GITHUB

        if uploaded_files or zip_bytes or local_dir:
            ul = UploadLoader()
            if uploaded_files:
                up_files = ul.load_from_dict(uploaded_files)
            elif zip_bytes:
                up_files = ul.load_from_zip(zip_bytes)
            else:
                up_files = ul.load_from_directory(local_dir)

            file_contents.update(up_files)
            analysis.uploaded_files = list(up_files.keys())
            analysis.input_mode = (
                Agent3InputMode.BOTH if github_url
                else Agent3InputMode.UPLOAD
            )

        if not file_contents:
            analysis.status      = "failed"
            analysis.fail_reason = "未提供任何代码输入（GitHub 链接或上传文件）"
            report.analysis = analysis
            logger.error("[Agent3] 无代码输入，退出")
            return report

        logger.info(f"[Agent3] 共加载 {len(file_contents)} 个代码文件")

        # ── 2. 关键文件筛选 ───────────────────────────────────────────
        selector     = FileSelector()
        all_paths    = list(file_contents.keys())
        key_files    = selector.select(all_paths, structure_hint)
        key_contents = {p: file_contents[p] for p, _ in key_files if p in file_contents}

        logger.info(f"[Agent3] 关键文件：{list(key_contents.keys())}")

        # ── 3. 静态分析 ───────────────────────────────────────────────
        analysis.components   = ArchExtractor().extract(key_contents)
        analysis.losses       = LossExtractor().extract(key_contents)
        analysis.train_config = ConfigExtractor().extract(key_contents)

        logger.info(
            f"[Agent3] 静态分析：{len(analysis.components)} 个组件，"
            f"{len(analysis.losses)} 个损失函数"
        )

        # ── 4. Claude API 语义理解 + 改进建议 ─────────────────────────
        if use_claude:
            import asyncio
            interpreter = CodeInterpreter(self.settings)
            if interpreter.enabled:
                await asyncio.to_thread(
                    interpreter.interpret,
                    analysis       = analysis,
                    file_contents  = key_contents,
                    sota_context   = agent2_summary,
                    structure_hint = structure_hint,
                )

        analysis.status = (
            "success" if (analysis.arch_summary or analysis.components)
            else "partial"
        )
        report.analysis = analysis

        # ── 5. 生成报告 ──────────────────────────────────────────────
        writer = ArchReportWriter()
        from config.settings import get_agent_output_dir
        writer.write_all(report, get_agent_output_dir(3))

        logger.info(f"[Agent3] 完成，状态：{analysis.status}")
        return report
