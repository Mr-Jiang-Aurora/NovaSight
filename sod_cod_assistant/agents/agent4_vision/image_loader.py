"""
图片加载与预处理
支持本地文件路径和字节流两种输入方式。
"""

import base64
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MAX_IMAGE_SIZE_MB = 20


class ImageLoader:
    """图片加载与预处理"""

    def load_from_path(self, image_path: str) -> Optional[dict]:
        """
        从本地文件路径加载图片，转为 base64。

        Returns:
            {"base64": str, "media_type": str, "path": str}
            失败返回 None
        """
        path = Path(image_path)
        if not path.exists():
            logger.error(f"图片文件不存在：{image_path}")
            return None

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_FORMATS:
            logger.error(f"不支持的图片格式：{suffix}")
            return None

        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_IMAGE_SIZE_MB:
            logger.warning(f"图片过大：{size_mb:.1f}MB > {MAX_IMAGE_SIZE_MB}MB")

        try:
            with open(path, "rb") as f:
                image_bytes = f.read()
            return self._to_base64_dict(image_bytes, suffix, str(path))
        except Exception as e:
            logger.error(f"图片读取失败：{e}")
            return None

    def load_from_bytes(
        self, image_bytes: bytes, filename: str = "image.png"
    ) -> Optional[dict]:
        """
        从字节流加载图片（Streamlit UI 上传场景）。

        Returns:
            {"base64": str, "media_type": str, "path": str}
        """
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_FORMATS:
            suffix = ".png"
        return self._to_base64_dict(image_bytes, suffix, filename)

    def _to_base64_dict(
        self, image_bytes: bytes, suffix: str, path: str
    ) -> dict:
        """转换为 base64 字典（Claude Vision API 格式）"""
        media_type_map = {
            ".png":  "image/png",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif":  "image/gif",
            ".bmp":  "image/png",
        }
        return {
            "base64":     base64.standard_b64encode(image_bytes).decode("utf-8"),
            "media_type": media_type_map.get(suffix, "image/png"),
            "path":       path,
        }
