"""
关键文件选择器
从文件树中识别出对架构分析最有价值的文件，
避免把所有文件都塞给 Claude API（控制成本和 Token 消耗）。
"""

import re
import logging

logger = logging.getLogger(__name__)

# 忽略列表（命中则跳过，不参与选择）
SKIP_PATTERNS = [
    r"test.*\.py$",
    r"__pycache__",
    r"\.git/",
    r"setup\.py$",
    r"setup_.*\.py$",
    r"demo.*\.py$",
    r"visuali[sz]e.*\.py$",
    r"eval.*\.py$",
    r"inference.*\.py$",
    r"predict.*\.py$",
]


def _should_skip(path: str) -> bool:
    """检查是否应跳过该文件（测试/demo/eval 等）"""
    for pat in SKIP_PATTERNS:
        if re.search(pat, path, re.IGNORECASE):
            return True
    return False


KEY_FILE_RULES: list[tuple[str, str, int]] = [
    # ── 最高优先（10）：明确的主网络文件 ──────────────────────────────
    (r"(?:^|/)(?:model|net|network)\.py$",                    "model_main", 10),
    (r"models?/.*(?:net|model|main|arch).*\.py$",             "model_main", 10),
    (r"(?:^|/)(?:main_model|base_model|cod_net|sod_net)\.py$","model_main", 10),
    # ── 高优先（9）：损失函数 ─────────────────────────────────────────
    (r"(?:^|/)loss(?:es)?\.py$",                              "loss",        9),
    (r"(?:^|/)(?:criterion|losses|loss_fn|custom_loss)\.py$", "loss",        9),
    (r"losses?/.*\.py$",                                      "loss",        9),
    # ── 高优先（8）：backbone / encoder / decoder ─────────────────────
    (r"(?:^|/)backbone.*\.py$",                               "backbone",    8),
    (r"(?:^|/)decoder.*\.py$",                                "decoder",     8),
    (r"(?:^|/)encoder.*\.py$",                                "encoder",     8),
    (r"backbones?/.*\.py$",                                   "backbone",    8),
    (r"(?:^|/)(?:swin|pvt|resnet|vgg|vit|convnext|efficientnet).*\.py$", "backbone", 8),
    # ── 中高优先（7）：模型目录 + 配置 ──────────────────────────────
    (r"models?/.*\.py$",                                      "model",       7),
    (r"networks?/.*\.py$",                                    "model",       7),
    (r"(?:^|/)(?:arch|structure|block|layer).*\.py$",         "model",       7),
    (r"configs?/.*\.(?:py|yaml|yml)$",                        "config",      7),
    (r"(?:^|/)(?:config|options|opts|params|hparams)\.(?:py|yaml|yml)$", "config", 7),
    # ── 中优先（6）：子模块 + 注意力 + 训练 ──────────────────────────
    (r"modules?/.*\.py$",                                     "module",      6),
    (r"(?:^|/)(?:attention|attn|transformer|mamba|ssm).*\.py$","module",     6),
    (r"(?:^|/)(?:neck|fpn|pafpn|bifpn|aspp|ppm).*\.py$",     "module",      6),
    (r"(?:^|/)train(?:er)?\.py$",                             "train",       6),
    (r"(?:^|/)(?:dataset|dataloader|data_utils).*\.py$",      "data",        5),
    # ── 低优先（5）：依赖说明 ─────────────────────────────────────────
    (r"requirements.*\.txt$",                                 "requirements",5),
    (r"(?:^|/)README.*\.(?:md|txt)$",                         "readme",      4),
    # ── 兜底（2）：任意 .py 文件（排除 __init__ / test / setup）────
    (r"(?<!__init__)(?<!test_)(?<!setup)\.py$",               "python",      2),
]

MAX_FILES = 30


class FileSelector:
    """关键文件选择器"""

    def select(
        self,
        file_tree: list[str],
        structure_hint: str = "",
    ) -> list[tuple[str, str]]:
        """
        从文件列表中选出最重要的文件。

        Args:
            file_tree:      文件路径列表
            structure_hint: Agent4 传入的结构描述（可选，提升选择准确性）

        Returns:
            [(file_path, type_label), ...] 按优先级降序
        """
        hinted_files = self._parse_structure_hint(structure_hint)

        scored: list[tuple[str, str, int]] = []
        for path in file_tree:
            # 跳过 test/demo/eval 等无关文件
            if _should_skip(path):
                continue

            # Agent4 提示的文件最高优先
            if path in hinted_files:
                scored.append((path, hinted_files[path], 15))
                continue

            best_score = 0
            best_label = "other"
            for pattern, label, score in KEY_FILE_RULES:
                if re.search(pattern, path, re.IGNORECASE):
                    if score > best_score:
                        best_score = score
                        best_label = label

            if best_score > 0:
                scored.append((path, best_label, best_score))

        scored.sort(key=lambda x: x[2], reverse=True)
        selected = [(p, lbl) for p, lbl, _ in scored[:MAX_FILES]]

        logger.info(
            f"文件选择：{len(file_tree)} 个文件 → 跳过 {len(file_tree) - len(scored)} 个"
            f" → 选出 {len(selected)} 个关键文件（上限 {MAX_FILES}）"
        )
        return selected

    def _parse_structure_hint(self, hint: str) -> dict[str, str]:
        """
        解析 Agent4 传来的结构提示，提取关键文件路径和类型。
        格式示例：
          "models/net.py 是主网络；backbone/swin.py 是骨干网络；loss.py 是损失函数"

        Returns:
            {file_path: type_label}
        """
        if not hint:
            return {}

        result = {}
        type_keywords = {
            "主网络": "model_main",
            "主模型": "model_main",
            "骨干":   "backbone",
            "backbone": "backbone",
            "decoder": "decoder",
            "解码器": "decoder",
            "损失":   "loss",
            "loss":   "loss",
            "配置":   "config",
            "config": "config",
            "训练":   "train",
        }

        segments = re.split(r"[；;\n]", hint)
        for seg in segments:
            seg = seg.strip()
            path_match = re.search(r"[\w./\-]+\.(?:py|yaml|yml|txt)", seg)
            if not path_match:
                continue
            file_path = path_match.group()
            for kw, label in type_keywords.items():
                if kw.lower() in seg.lower():
                    result[file_path] = label
                    break

        return result
