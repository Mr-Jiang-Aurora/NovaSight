"""
模式B：本地上传代码加载器
用户直接上传 .py 文件（或 zip 包），Agent3 读取后分析。

处理两种上传方式：
  1. 直接传入文件内容字典（Streamlit UI 用，file_uploader 返回的内容）
  2. 读取本地目录（测试脚本用）
"""

import io
import os
import zipfile
import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".py", ".yaml", ".yml", ".txt", ".cfg", ".json", ".toml", ".ini"}
MAX_LINES_PER_FILE = 3000   # 单文件截断上限（总行数由 code_interpreter 的 max_code_lines 控制）
MAX_FILES_FROM_UPLOAD = 30  # 本地上传最多处理的文件数


class UploadLoader:
    """本地上传代码加载器（模式B）"""

    def load_from_dict(
        self, uploaded_files: dict[str, bytes]
    ) -> dict[str, str]:
        """
        从 Streamlit file_uploader 返回的字典加载代码。

        Args:
            uploaded_files: {filename: file_bytes}

        Returns:
            {file_path: file_content}
        """
        contents = {}
        # 按扩展名优先级排序（.py 优先）
        sorted_files = sorted(
            uploaded_files.items(),
            key=lambda kv: (0 if Path(kv[0]).suffix == ".py" else 1, kv[0])
        )
        for filename, file_bytes in sorted_files:
            if len(contents) >= MAX_FILES_FROM_UPLOAD:
                logger.info(f"已达到上传文件上限 {MAX_FILES_FROM_UPLOAD}，跳过剩余文件")
                break
            ext = Path(filename).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            try:
                text = file_bytes.decode("utf-8", errors="replace")
                contents[filename] = self._truncate(text)
                logger.debug(f"加载文件：{filename} ({len(text.splitlines())} 行)")
            except Exception as e:
                logger.warning(f"文件读取失败 {filename}: {e}")

        logger.info(f"上传加载完成：{len(contents)} 个文件")
        return contents

    def load_from_zip(self, zip_bytes: bytes) -> dict[str, str]:
        """
        从 zip 包字节流加载代码（用户打包上传整个项目）。

        Args:
            zip_bytes: zip 文件的字节内容

        Returns:
            {file_path: file_content}
        """
        contents = {}
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for zip_info in zf.infolist():
                    if zip_info.is_dir():
                        continue
                    path = zip_info.filename
                    ext  = Path(path).suffix.lower()
                    if ext not in SUPPORTED_EXTENSIONS:
                        continue
                    if any(
                        x in path for x in
                        ["__pycache__", ".git", ".egg-info", "node_modules"]
                    ):
                        continue
                    try:
                        raw  = zf.read(zip_info.filename)
                        text = raw.decode("utf-8", errors="replace")
                        contents[path] = self._truncate(text)
                    except Exception as e:
                        logger.debug(f"zip 内文件读取失败 {path}: {e}")

        except zipfile.BadZipFile:
            logger.error("无效的 zip 文件")

        logger.info(f"zip 加载完成：{len(contents)} 个文件")
        return contents

    def load_from_directory(self, dir_path: str) -> dict[str, str]:
        """
        从本地目录读取代码（测试/开发时使用）。

        Args:
            dir_path: 本地代码目录路径

        Returns:
            {relative_file_path: file_content}
        """
        contents = {}
        root = Path(dir_path)

        if not root.exists():
            logger.error(f"目录不存在：{dir_path}")
            return {}

        for fpath in root.rglob("*"):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            parts = fpath.parts
            if any(
                x in parts for x in
                ["__pycache__", ".git", ".venv", "venv", "node_modules"]
            ):
                continue
            try:
                rel_path = str(fpath.relative_to(root))
                text = fpath.read_text(encoding="utf-8", errors="replace")
                contents[rel_path] = self._truncate(text)
            except Exception as e:
                logger.debug(f"文件读取失败 {fpath}: {e}")

        logger.info(f"目录加载完成：{dir_path}，共 {len(contents)} 个文件")
        return contents

    def load_from_structure_hint(self, hint_text: str) -> str:
        """
        接收 Agent4 传来的目录结构描述文字。
        （Agent4 联动接口，当前阶段仅做存储，不做实际处理）

        Args:
            hint_text: 如 "models/net.py 是主网络；backbone/swin.py 是骨干网络；..."

        Returns:
            原始 hint_text（传递给 code_interpreter.py 使用）
        """
        logger.info(
            f"收到 Agent4 结构提示：{hint_text[:100]}..."
            if len(hint_text) > 100 else f"收到 Agent4 结构提示：{hint_text}"
        )
        return hint_text

    def _truncate(self, text: str) -> str:
        """截断过长文件（保留前 MAX_LINES_PER_FILE 行）"""
        lines = text.splitlines()
        if len(lines) > MAX_LINES_PER_FILE:
            return "\n".join(lines[:MAX_LINES_PER_FILE]) + "\n...[已截断]"
        return text
