"""训练配置提取器"""

import re
import logging
from typing import Optional
from shared.models import TrainConfig

logger = logging.getLogger(__name__)


class ConfigExtractor:
    """训练配置提取器"""

    def extract(self, file_contents: dict[str, str]) -> Optional[TrainConfig]:
        configs = []
        for file_path, content in file_contents.items():
            if not content:
                continue
            is_config = any(
                x in file_path.lower()
                for x in [".yaml", ".yml", "config", "train", "option"]
            )
            if not is_config:
                continue
            cfg = self._extract_from_content(file_path, content)
            if cfg:
                configs.append(cfg)

        if not configs:
            return None

        return max(configs, key=lambda c: sum(
            1 for f in ["batch_size", "learning_rate", "epochs", "optimizer"]
            if getattr(c, f) is not None
        ))

    def _extract_from_content(
        self, file_path: str, content: str
    ) -> Optional[TrainConfig]:
        cfg = TrainConfig(config_file=file_path)
        patterns = {
            "batch_size":    r"batch[_\s]?size\s*[=:]\s*(\d+)",
            "learning_rate": r"(?:lr|learning[_\s]?rate)\s*[=:]\s*([\d.e\-]+)",
            "epochs":        r"(?:epochs?|num[_\s]?epochs?|max[_\s]?epochs?)\s*[=:]\s*(\d+)",
            "optimizer":     r"(?:optimizer|optim)\s*[=:]\s*['\"]?(\w+)",
            "input_size":    r"(?:input[_\s]?size|img[_\s]?size|trainsize)\s*[=:]\s*(\d+)",
            "lr_scheduler":  r"(?:scheduler|lr[_\s]?scheduler)\s*[=:]\s*['\"]?(\w+)",
        }
        for field, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if not match:
                continue
            val = match.group(1)
            if field in ("batch_size", "epochs", "input_size"):
                try:
                    setattr(cfg, field, int(val))
                except ValueError:
                    pass
            elif field == "learning_rate":
                try:
                    setattr(cfg, field, float(val))
                except ValueError:
                    pass
            else:
                setattr(cfg, field, val)

        has_any = any(
            getattr(cfg, f) is not None
            for f in ["batch_size", "learning_rate", "epochs"]
        )
        return cfg if has_any else None
