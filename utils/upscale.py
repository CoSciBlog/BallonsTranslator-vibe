from pathlib import Path
from typing import Tuple

import cv2
import numpy as np


QUALITY_INTERPOLATION = {
    "fast": cv2.INTER_LINEAR,
    "balanced": cv2.INTER_CUBIC,
    "quality": cv2.INTER_LANCZOS4,
    "animesharp": cv2.INTER_LANCZOS4,
}

ARTIFACT_REDUCTION_STRENGTH = {
    "off": 0,
    "light": 3,
    "medium": 6,
    "strong": 10,
}


def reduce_compression_artifacts(img: np.ndarray, strength: str = "off") -> np.ndarray:
    """Reduce block/ringing artifacts before enlargement while retaining line art."""
    denoise_strength = ARTIFACT_REDUCTION_STRENGTH.get((strength or "off").lower(), 0)
    if img is None or denoise_strength <= 0:
        return img
    alpha = None
    source = img
    if img.ndim == 3 and img.shape[2] == 4:
        source, alpha = img[:, :, :3], img[:, :, 3:4]
    if source.ndim == 2:
        cleaned = cv2.fastNlMeansDenoising(source, None, denoise_strength, 7, 21)
    else:
        cleaned = cv2.fastNlMeansDenoisingColored(
            source, None, denoise_strength, denoise_strength, 7, 21
        )
    return np.concatenate([cleaned, alpha], axis=2) if alpha is not None else cleaned


def project_upscale_filename(imgname: str, factor: float) -> str:
    factor_tag = f"{float(factor):.2f}".rstrip("0").rstrip(".").replace(".", "_")
    source = Path(imgname)
    return f"{source.stem}_upscaled_{factor_tag}x{source.suffix}"


def filename_has_upscale_marker(imgname: str) -> bool:
    return "upscaled" in Path(imgname).stem.lower()


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
    artifact_reduction: str = "off",
) -> Tuple[np.ndarray, float]:
    if img is None or factor <= 1:
        return img, 1.0

    height, width = img.shape[:2]
    new_width = max(1, int(round(width * factor)))
    new_height = max(1, int(round(height * factor)))
    if new_width == width and new_height == height:
        return img, 1.0

    img = reduce_compression_artifacts(img, artifact_reduction)
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
