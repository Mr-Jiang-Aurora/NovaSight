"""
架构组件提取器（AST 静态分析）
从 Python 代码中提取模型架构信息，不需要执行代码。
"""

import ast
import re
import logging
from shared.models import ArchComponent

logger = logging.getLogger(__name__)

BACKBONE_KEYWORDS: dict[str, str] = {
    "swin":         "Swin Transformer",
    "vit":          "Vision Transformer",
    "pvt":          "PVT",
    "resnet":       "ResNet",
    "res2net":      "Res2Net",
    "convnext":     "ConvNeXt",
    "efficientnet": "EfficientNet",
    "internimage":  "InternImage",
    "mamba":        "Mamba (SSM)",
    "vmamba":       "VMamba",
    "mobilenet":    "MobileNet",
    "densenet":     "DenseNet",
    "vgg":          "VGG",
}

NECK_KEYWORDS: dict[str, str] = {
    "fpn":  "FPN",
    "bifpn":"BiFPN",
    "aspp": "ASPP",
    "ppm":  "PPM",
    "pafpn":"PAFPN",
}

INNOVATION_HINTS = [
    "attention", "gate", "enhance", "fuse", "align",
    "adaptive", "dynamic", "calibrat", "interact",
    "discriminat", "refine", "aggregate", "routing",
    "prompt", "bridge", "cam", "camo", "decode",
    "cross", "dual", "multi", "mutual",
]


class ArchExtractor:
    """架构组件提取器"""

    def extract(self, file_contents: dict[str, str]) -> list[ArchComponent]:
        """从多个文件中提取所有架构组件"""
        components = []
        seen = set()

        for file_path, content in file_contents.items():
            if not content:
                continue
            for comp in self._extract_from_file(file_path, content):
                key = (comp.component_type, comp.name)
                if key not in seen:
                    seen.add(key)
                    components.append(comp)

        return components

    def _extract_from_file(
        self, file_path: str, content: str
    ) -> list[ArchComponent]:
        found = []
        content_lower = content.lower()

        # 1. 识别 Backbone
        for kw, std_name in BACKBONE_KEYWORDS.items():
            if kw in content_lower and content_lower.count(kw) >= 2:
                is_pretrained = any(
                    x in content_lower for x in
                    ["pretrained", "from_pretrained", "load_state_dict", "imagenet"]
                )
                found.append(ArchComponent(
                    component_type="backbone",
                    name=std_name,
                    source_file=file_path,
                    is_pretrained=is_pretrained,
                    pretrained_on="ImageNet" if is_pretrained else None,
                ))
                break

        # 2. 识别 Neck
        for kw, std_name in NECK_KEYWORDS.items():
            if kw in content_lower and content_lower.count(kw) >= 2:
                found.append(ArchComponent(
                    component_type="neck",
                    name=std_name,
                    source_file=file_path,
                ))

        # 3. 识别用户自定义模块（AST 解析 nn.Module 子类）
        found.extend(self._extract_custom_modules(file_path, content))

        return found

    def _extract_custom_modules(
        self, file_path: str, content: str
    ) -> list[ArchComponent]:
        """通过 AST 解析识别自定义 nn.Module 子类"""
        found = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            is_module = any(
                "module" in str(getattr(b, 'attr', '') or getattr(b, 'id', '')).lower()
                for b in node.bases
            )
            if not is_module:
                continue

            class_name = node.name
            if any(kw in class_name.lower() for kw in BACKBONE_KEYWORDS):
                continue
            is_innovative = any(h in class_name.lower() for h in INNOVATION_HINTS)
            if is_innovative:
                found.append(ArchComponent(
                    component_type="module",
                    name=class_name,
                    source_file=file_path,
                    class_name=class_name,
                    line_number=node.lineno,
                ))

        return found[:6]
