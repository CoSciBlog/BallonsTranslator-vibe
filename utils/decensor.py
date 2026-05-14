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


def _candidate_components(
    mask: np.ndarray,
    min_area_ratio: float,
    max_area_ratio: float = 0.18,
    min_fill: float = 0.25,
    min_size: int = 8,
    aspect_min: float = 0.0,
    aspect_max: float = 999.0,
    fill_rect: bool = False,
) -> np.ndarray:
    h, w = mask.shape[:2]
    min_area = max(16, int(h * w * max(min_area_ratio, 0.0)))
    max_area = max(min_area, int(h * w * max_area_ratio))
    contours, _ = cv2.findContours((mask > 0).astype(np.uint8) * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filtered = np.zeros_like(mask, dtype=np.uint8)

    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if area < min_area or area > max_area or bw < min_size or bh < min_size:
            continue
        if x <= 1 or y <= 1 or x + bw >= w - 2 or y + bh >= h - 2:
            continue

        fill = area / max(bw * bh, 1)
        aspect = bw / max(bh, 1)
        if fill < min_fill or aspect < aspect_min or aspect > aspect_max:
            continue

        if fill_rect:
            cv2.rectangle(filtered, (x, y), (x + bw, y + bh), 255, thickness=cv2.FILLED)
        else:
            cv2.drawContours(filtered, [contour], -1, 255, thickness=cv2.FILLED)

    return filtered


def _merge_close_components(mask: np.ndarray, kernels) -> np.ndarray:
    merged = np.zeros_like(mask, dtype=np.uint8)
    for ksize in kernels:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, ksize)
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        merged = cv2.bitwise_or(merged, closed)
    return merged


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
    dark = (gray < 70) & (saturation < 140)
    light = (gray > 222) & (saturation < 70)
    h, w = gray.shape[:2]
    h_kernel = max(21, min(121, w // 35))
    v_kernel = max(21, min(121, h // 35))
    kernels = [
        (31, 5),
        (51, 7),
        (h_kernel, 9),
        (5, 31),
        (7, 51),
        (9, v_kernel),
    ]
    combined = np.zeros_like(gray, dtype=np.uint8)
    for raw_mask in (dark.astype(np.uint8) * 255, light.astype(np.uint8) * 255):
        merged = _merge_close_components(raw_mask, kernels)
        merged = cv2.morphologyEx(merged, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)
        horizontal = _candidate_components(
            merged,
            min_area_ratio,
            max_area_ratio=0.08,
            min_fill=0.40,
            min_size=10,
            aspect_min=1.8,
            fill_rect=True,
        )
        vertical = _candidate_components(
            merged,
            min_area_ratio,
            max_area_ratio=0.08,
            min_fill=0.40,
            min_size=10,
            aspect_max=0.55,
            fill_rect=True,
        )
        combined = cv2.bitwise_or(combined, cv2.bitwise_or(horizontal, vertical))
    return combined


def mosaic_mask(img: np.ndarray, min_area_ratio: float = 0.0001) -> np.ndarray:
    rgb = _rgb(img)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape[:2]
    if h < 32 or w < 32:
        return np.zeros((h, w), dtype=np.uint8)

    accum = np.zeros((h, w), dtype=np.uint8)
    rgb_f = rgb.astype(np.float32)
    for block in (4, 6, 8, 10, 12, 16, 20, 24, 32):
        small_w = max(1, w // block)
        small_h = max(1, h // block)
        coarse = cv2.resize(rgb, (small_w, small_h), interpolation=cv2.INTER_AREA)
        restored = cv2.resize(coarse, (w, h), interpolation=cv2.INTER_NEAREST)
        diff = np.mean(np.abs(rgb_f - restored.astype(np.float32)), axis=2)
        local_mean = cv2.blur(gray.astype(np.float32), (block, block))
        local_sq_mean = cv2.blur((gray.astype(np.float32) ** 2), (block, block))
        local_std = np.sqrt(np.maximum(local_sq_mean - local_mean ** 2, 0))
        candidate = ((diff < max(6, block * 0.75)) & (local_std > 5)).astype(np.uint8) * 255
        accum = cv2.bitwise_or(accum, candidate)

    accum = cv2.morphologyEx(accum, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)
    accum = _merge_close_components(accum, [(9, 9), (15, 15), (21, 21)])
    return _candidate_components(
        accum,
        min_area_ratio,
        max_area_ratio=0.16,
        min_fill=0.20,
        min_size=12,
        aspect_min=0.25,
        aspect_max=4.0,
        fill_rect=False,
    )


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
