"""
模式A：GitHub 代码加载器
用户提供自己代码仓库的 GitHub 链接，Agent3 通过 API 拉取代码。

支持格式：
  https://github.com/owner/repo
  https://github.com/owner/repo/tree/branch
  https://github.com/owner/repo/tree/branch/subdir
"""

import re
import base64
import asyncio
import logging
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com"

MAX_LINES_PER_FILE = 3000     # 单文件截断行数（总行数由 CodeInterpreter 控制）
CONCURRENT_DOWNLOADS = 8      # 并发下载数（有 token 时可更高）


class GitHubLoader:
    """GitHub 代码加载器（模式A）"""

    def __init__(self, github_token: str = ""):
        self.token = github_token
        self.headers = {
            "Accept":     "application/vnd.github.v3+json",
            "User-Agent": "SOD-COD-Research-Assistant/1.0",
        }
        if github_token:
            self.headers["Authorization"] = f"token {github_token}"

    def parse_url(self, url: str) -> Optional[tuple[str, str, str]]:
        """
        从 GitHub URL 提取 owner、repo_name 和 branch。

        支持：
          https://github.com/owner/repo
          https://github.com/owner/repo/tree/main
          https://github.com/owner/repo/tree/dev/subdir

        Returns:
            (owner, repo, branch)，branch 为 None 表示用默认分支
        """
        url = url.strip().replace(" ", "")
        # 带 tree/branch 的 URL
        m = re.search(
            r"github\.com[/:]([^/\s]+)/([^/\s]+)/tree/([^/\s]+)",
            url, re.IGNORECASE
        )
        if m:
            return m.group(1), m.group(2).rstrip(".git"), m.group(3)
        # 普通 URL
        m = re.search(r"github\.com[/:]([^/\s]+)/([^/\s\.]+)", url)
        if m:
            return m.group(1), m.group(2).rstrip(".git"), None
        return None

    async def load(self, github_url: str, structure_hint: str = "") -> dict[str, str]:
        """
        主入口：从 GitHub 仓库加载关键代码文件。

        Args:
            github_url:     仓库 URL（支持带 branch 的格式）
            structure_hint: Agent4 传入的结构提示（可选，提升文件选择准确性）

        Returns:
            {file_path: file_content}，失败时返回空字典
        """
        github_url = github_url.strip().replace(" ", "")
        parsed = self.parse_url(github_url)
        if not parsed:
            logger.error(f"无法解析 GitHub URL：{github_url}")
            return {}

        owner, repo, branch = parsed
        logger.info(
            f"开始拉取代码：{owner}/{repo}"
            + (f" (分支: {branch})" if branch else " (默认分支)")
        )

        # 解析默认分支
        if not branch:
            branch = await self._get_default_branch(owner, repo) or "main"
            logger.info(f"默认分支：{branch}")

        file_tree = await self._fetch_file_tree(owner, repo, branch)
        if not file_tree:
            logger.warning(f"文件树为空，尝试 master 分支")
            fallback = "master" if branch == "main" else "main"
            file_tree = await self._fetch_file_tree(owner, repo, fallback)
            if file_tree:
                branch = fallback

        if not file_tree:
            logger.error(f"无法获取文件树：{owner}/{repo}")
            return {}

        logger.info(f"文件树：{len(file_tree)} 个文件")

        from agents.agent3_code.file_selector import FileSelector
        selector  = FileSelector()
        key_files = selector.select(file_tree, structure_hint)
        logger.info(f"选出 {len(key_files)} 个关键文件，开始并发下载")

        file_contents: dict[str, str] = {}
        semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOADS)

        async def fetch_one(path: str):
            async with semaphore:
                content = await self._fetch_file(owner, repo, branch, path)
                await asyncio.sleep(0.1)
                return path, content

        tasks   = [fetch_one(p) for p, _ in key_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.debug(f"下载异常：{result}")
                continue
            path, content = result
            if content:
                file_contents[path] = content

        total_lines = sum(c.count("\n") for c in file_contents.values())
        logger.info(
            f"下载完成：{len(file_contents)}/{len(key_files)} 个文件，"
            f"共约 {total_lines} 行"
        )
        return file_contents

    async def _get_default_branch(self, owner: str, repo: str) -> Optional[str]:
        """获取仓库的默认分支名称"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("default_branch")
        except Exception:
            pass
        return None

    async def _fetch_file_tree(
        self, owner: str, repo: str, branch: str
    ) -> list[str]:
        """获取仓库文件树（路径列表），自动处理超大仓库的 truncated 情况"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 403:
                        logger.warning(
                            "⚠️ GitHub API 速率限制（60次/小时），建议配置 GITHUB_TOKEN 提升至 5000次/小时\n"
                            "获取方式：GitHub → Settings → Developer settings → "
                            "Personal access tokens → 勾选 public_repo"
                        )
                        return []
                    if resp.status == 404:
                        logger.warning(f"仓库或分支不存在：{owner}/{repo}@{branch}")
                        return []
                    if resp.status != 200:
                        logger.warning(f"文件树请求失败，HTTP {resp.status}")
                        return []
                    data = await resp.json()

            if data.get("truncated"):
                logger.warning(
                    "⚠️ 仓库文件数超过 GitHub API 上限（100,000），文件树已被截断，"
                    "Agent3 将在截断范围内选取关键文件"
                )

            return [
                item["path"] for item in data.get("tree", [])
                if item.get("type") == "blob"
            ]
        except Exception as e:
            logger.error(f"文件树获取失败：{e}")
            return []

    async def _fetch_file(
        self, owner: str, repo: str, branch: str, path: str
    ) -> Optional[str]:
        """
        下载单个文件内容。
        策略：优先 GitHub Contents API（Base64解码），失败降级到 raw CDN。
        """
        # ── 方式1：GitHub Contents API（更稳定，支持私有仓库）──────────
        api_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(
                    api_url, timeout=aiohttp.ClientTimeout(total=25)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # 跳过大文件（size 单位 bytes，超过 300KB 不下载）
                        if data.get("size", 0) > 300 * 1024:
                            logger.debug(f"跳过大文件（>{300}KB）：{path}")
                            return None
                        raw_bytes = base64.b64decode(
                            data.get("content", "").replace("\n", "")
                        )
                        text = raw_bytes.decode("utf-8", errors="replace")
                        return self._truncate(text, path)
        except Exception as e:
            logger.debug(f"Contents API 下载失败 {path}: {e}，降级到 raw CDN")

        # ── 方式2：raw.githubusercontent.com（公开仓库兜底）────────────
        raw_url = f"{GITHUB_RAW_BASE}/{owner}/{repo}/{branch}/{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    raw_url, timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status != 200:
                        return None
                    text = await resp.text(encoding="utf-8", errors="replace")
                    return self._truncate(text, path)
        except Exception as e:
            logger.debug(f"raw CDN 下载也失败 {path}: {e}")
            return None

    @staticmethod
    def _truncate(text: str, path: str = "") -> str:
        """截断超长文件，保留前 MAX_LINES_PER_FILE 行"""
        lines = text.splitlines()
        if len(lines) > MAX_LINES_PER_FILE:
            logger.debug(f"截断文件 {path}：{len(lines)} → {MAX_LINES_PER_FILE} 行")
            return (
                "\n".join(lines[:MAX_LINES_PER_FILE])
                + f"\n# ...[已截断，原文件 {len(lines)} 行，仅保留前 {MAX_LINES_PER_FILE} 行]"
            )
        return text
