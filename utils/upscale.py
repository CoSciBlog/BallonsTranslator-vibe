from typing import Tuple

import cv2
import numpy as np


QUALITY_INTERPOLATION = {
    "fast": cv2.INTER_LINEAR,
    "balanced": cv2.INTER_CUBIC,
    "quality": cv2.INTER_LANCZOS4,
    "animesharp": cv2.INTER_LANCZOS4,
}


def effective_upscale_factor(
    width: int,
    height: int,
    factor: float,
    min_long_edge: int,
    max_long_edge: int,
) -> float:
    if factor <= 1:
        return 1.0
    long_edge = max(width, height)
    if min_long_edge > 0 and long_edge > min_long_edge:
        return 1.0
    if max_long_edge > 0:
        factor = min(factor, max_long_edge / max(long_edge, 1))
    return max(factor, 1.0)


def upscale_image(
    img: np.ndarray,
    factor: float,
    quality: str = "balanced",
) -> Tuple[np.ndarray, float]:
    if img is None or factor <= 1:
        return img, 1.0

    height, width = img.shape[:2]
    new_width = max(1, int(round(width * factor)))
    new_height = max(1, int(round(height * factor)))
    if new_width == width and new_height == height:
        return img, 1.0

    quality = (quality or "balanced").lower()
    interpolation = QUALITY_INTERPOLATION.get(quality, cv2.INTER_CUBIC)
    result = cv2.resize(img, (new_width, new_height), interpolation=interpolation)

    if quality in {"balanced", "quality", "animesharp"}:
        amount = {"balanced": 0.18, "quality": 0.28, "animesharp": 0.42}[quality]
        blurred = cv2.GaussianBlur(result, (0, 0), sigmaX=0.8)
        result = cv2.addWeighted(result, 1.0 + amount, blurred, -amount, 0)

    if quality == "animesharp":
        smooth = cv2.bilateralFilter(result, d=5, sigmaColor=18, sigmaSpace=18)
        result = cv2.addWeighted(result, 0.75, smooth, 0.25, 0)

    return result, factor
