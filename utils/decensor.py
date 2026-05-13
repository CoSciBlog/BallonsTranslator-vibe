from typing import Tuple

import cv2
import numpy as np


def _rgb(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    return img[:, :, :3]


def _filter_components(mask: np.ndarray, min_area_ratio: float) -> np.ndarray:
    h, w = mask.shape[:2]
    min_area = max(16, int(h * w * max(min_area_ratio, 0.0)))
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    filtered = np.zeros_like(mask, dtype=np.uint8)
    for label in range(1, num_labels):
        x, y, bw, bh, area = stats[label]
        if area < min_area:
            continue
        fill = area / max(bw * bh, 1)
        aspect = bw / max(bh, 1)
        if fill >= 0.25 or aspect >= 2.5 or aspect <= 0.4:
            filtered[labels == label] = 255
    return filtered


def green_mask(img: np.ndarray, min_area_ratio: float = 0.00005) -> np.ndarray:
    rgb = _rgb(img)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    mask = (
        (g > 170)
        & (r < 120)
        & (b < 140)
        & ((g.astype(np.int16) - r.astype(np.int16)) > 70)
        & ((g.astype(np.int16) - b.astype(np.int16)) > 60)
    )
    return _filter_components(mask.astype(np.uint8) * 255, min_area_ratio)


def bar_mask(img: np.ndarray, min_area_ratio: float = 0.00005) -> np.ndarray:
    rgb = _rgb(img)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    saturation = hsv[:, :, 1]
    dark = (gray < 45) & (saturation < 90)
    light = (gray > 230) & (saturation < 45)
    mask = (dark | light).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    h, w = mask.shape[:2]
    min_area = max(16, int(h * w * max(min_area_ratio, 0.0)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filtered = np.zeros_like(mask, dtype=np.uint8)
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if area < min_area or bw < 4 or bh < 4:
            continue
        if x <= 1 or y <= 1 or x + bw >= w - 2 or y + bh >= h - 2:
            continue
        aspect = bw / max(bh, 1)
        fill = area / max(bw * bh, 1)
        if fill >= 0.55 and (aspect >= 3.0 or aspect <= 0.33):
            cv2.drawContours(filtered, [contour], -1, 255, thickness=cv2.FILLED)
    return filtered


def mosaic_mask(img: np.ndarray, min_area_ratio: float = 0.0001) -> np.ndarray:
    rgb = _rgb(img)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape[:2]
    if h < 32 or w < 32:
        return np.zeros((h, w), dtype=np.uint8)

    accum = np.zeros((h, w), dtype=np.uint8)
    for block in (6, 8, 10, 12, 16):
        small_w = max(1, w // block)
        small_h = max(1, h // block)
        coarse = cv2.resize(gray, (small_w, small_h), interpolation=cv2.INTER_AREA)
        restored = cv2.resize(coarse, (w, h), interpolation=cv2.INTER_NEAREST)
        diff = cv2.absdiff(gray, restored)
        local_mean = cv2.blur(gray.astype(np.float32), (block, block))
        local_sq_mean = cv2.blur((gray.astype(np.float32) ** 2), (block, block))
        local_std = np.sqrt(np.maximum(local_sq_mean - local_mean ** 2, 0))
        candidate = ((diff < 4) & (local_std > 10)).astype(np.uint8) * 255
        accum = cv2.bitwise_or(accum, candidate)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    accum = cv2.morphologyEx(accum, cv2.MORPH_OPEN, kernel, iterations=1)
    accum = cv2.morphologyEx(accum, cv2.MORPH_CLOSE, kernel, iterations=2)
    return _filter_components(accum, min_area_ratio)


def build_decensor_mask(
    img: np.ndarray,
    mode: str = "auto",
    dilate: int = 8,
    min_area_ratio: float = 0.00005,
) -> Tuple[np.ndarray, str]:
    mode = (mode or "auto").lower()
    if mode not in {"auto", "green", "bars", "mosaic"}:
        mode = "auto"
    h, w = img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    if mode in {"auto", "green"}:
        mask = cv2.bitwise_or(mask, green_mask(img, min_area_ratio))
    if mode in {"auto", "bars"}:
        mask = cv2.bitwise_or(mask, bar_mask(img, min_area_ratio))
    if mode in {"auto", "mosaic"}:
        mask = cv2.bitwise_or(mask, mosaic_mask(img, max(min_area_ratio, 0.0001)))

    dilate = max(0, int(dilate))
    if dilate > 0 and np.any(mask > 0):
        k = dilate * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        mask = cv2.dilate(mask, kernel, iterations=1)

    return (mask > 0).astype(np.uint8) * 255, mode
