"""损失函数提取器"""

import re
import logging
from shared.models import LossConfig

logger = logging.getLogger(__name__)

LOSS_KEYWORDS: dict[str, str] = {
    "bceloss":        "BCE Loss",
    "bcewithlogits":  "BCE with Logits",
    "bce_loss":       "BCE Loss",
    "iou_loss":       "IoU Loss",
    "iouloss":        "IoU Loss",
    "diceloss":       "Dice Loss",
    "dice_loss":      "Dice Loss",
    "focal_loss":     "Focal Loss",
    "focalloss":      "Focal Loss",
    "ssim_loss":      "SSIM Loss",
    "ssimloss":       "SSIM Loss",
    "structure_loss": "Structure Loss (BCE+IoU)",
    "edge_loss":      "Edge Loss",
    "edgeloss":       "Edge Loss",
    "mse_loss":       "MSE Loss",
    "mseloss":        "MSE Loss",
    "l1_loss":        "L1 Loss",
    "smoothl1":       "Smooth L1 Loss",
}


class LossExtractor:
    """损失函数提取器"""

    def extract(self, file_contents: dict[str, str]) -> list[LossConfig]:
        """从多个文件中提取损失函数"""
        all_losses = []
        seen = set()

        for file_path, content in file_contents.items():
            if not content:
                continue
            is_loss_file = any(
                x in file_path.lower() for x in ["loss", "criterion", "train"]
            )
            for loss in self._extract_from_file(file_path, content, is_loss_file):
                if loss.loss_name not in seen:
                    seen.add(loss.loss_name)
                    all_losses.append(loss)

        return all_losses

    def _extract_from_file(
        self, file_path: str, content: str, is_loss_file: bool
    ) -> list[LossConfig]:
        found = []
        content_lower = content.lower()

        for kw, std_name in LOSS_KEYWORDS.items():
            if kw not in content_lower:
                continue
            if not is_loss_file and content_lower.count(kw) < 2:
                continue

            weight = self._extract_weight(content, kw)
            is_aux = bool(re.search(
                rf"(aux|side|deep|supervision).*{re.escape(kw)}", content_lower
            ))
            found.append(LossConfig(
                loss_name=std_name, weight=weight,
                source_file=file_path, is_auxiliary=is_aux,
            ))

        return found

    def _extract_weight(self, content: str, kw: str) -> float:
        match = re.search(
            rf"([\d.]+)\s*\*\s*.*{re.escape(kw)}", content.lower()
        )
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return 1.0
