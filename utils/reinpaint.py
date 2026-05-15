from typing import Iterable, Optional, Sequence, Tuple

import cv2
import numpy as np


def normalize_inpaint_mask(mask: Optional[np.ndarray], shape: Sequence[int]) -> Optional[np.ndarray]:
    if mask is None:
        return None
    mask = np.asarray(mask)
    if mask.ndim == 3:
        mask = mask[..., 0]
    target_h, target_w = int(shape[0]), int(shape[1])
    if mask.shape[:2] != (target_h, target_w):
        mask = cv2.resize(mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
    return ((mask > 0).astype(np.uint8) * 255)


def combine_inpaint_masks(
    masks: Iterable[Optional[np.ndarray]],
    shape: Sequence[int],
    dilate: int = 0,
) -> Optional[np.ndarray]:
    combined = np.zeros((int(shape[0]), int(shape[1])), dtype=np.uint8)
    found = False
    for mask in masks:
        normalized = normalize_inpaint_mask(mask, combined.shape)
        if normalized is None or not np.any(normalized > 0):
            continue
        combined = cv2.bitwise_or(combined, normalized)
        found = True
    if not found:
        return None
    dilate = max(0, int(dilate))
    if dilate > 0:
        element = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (2 * dilate + 1, 2 * dilate + 1),
            (dilate, dilate),
        )
        combined = cv2.dilate(combined, element)
    return ((combined > 0).astype(np.uint8) * 255)


def mask_bounding_rect(mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    normalized = normalize_inpaint_mask(mask, mask.shape[:2])
    if normalized is None:
        return None
    points = cv2.findNonZero(normalized)
    if points is None:
        return None
    x, y, w, h = cv2.boundingRect(points)
    return x, y, x + w, y + h
