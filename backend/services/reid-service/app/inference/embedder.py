"""Appearance embedding extraction -- ImageNet-pretrained ResNet-50 with its
classification head removed, used as a generic feature extractor. For
Person Re-ID (M16) this is doc11 §2's explicitly documented fallback
("ResNet-50-based Re-ID embedding (simpler, larger, still effective)"), not
the "Primary" OSNet/TorchReID-family model doc11 recommends -- because no
fine-tuned person-Re-ID weights or training data exist for this deployment.

Vehicle Re-ID (M17) reuses this exact same instance rather than loading a
second model: doc11 §2's own fallback for the vehicle table is "reuse a
general image-embedding model...as a lower-accuracy stopgap" when no
vehicle-specific Re-ID model exists (true here too) -- this class already
is a general-purpose image embedder (nothing about it is person-specific),
so it satisfies that fallback for both tables without a second model in
memory. It's a real, standard, legitimate technique (off-the-shelf CNN
features for image similarity/retrieval), just not specialized for Re-ID
the way OSNet or a vehicle-Re-ID network is; expect doc11's own "real-world
cross-camera accuracy is typically well below benchmark numbers" caveat to
apply here more than usual. Swapping in a real Re-ID model later only means
replacing this one class (or adding a second one, per-object-type).
"""

from __future__ import annotations

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision.models import ResNet50_Weights, resnet50


class ImageEmbedder:
    def __init__(self) -> None:
        weights = ResNet50_Weights.IMAGENET1K_V2
        model = resnet50(weights=weights)
        model.fc = torch.nn.Identity()  # drop the 1000-class classification head
        model.eval()
        self._model = model
        self._transforms = weights.transforms()

    def embed(self, bgr_crop: np.ndarray) -> list[float]:
        rgb = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        tensor = self._transforms(image).unsqueeze(0)
        with torch.no_grad():
            features = self._model(tensor)
        vector = features.squeeze(0).numpy()
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector.tolist()
