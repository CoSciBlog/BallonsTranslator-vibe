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


def reinpaint_project_page(
    project,
    inpainter,
    page_name: str,
    dilate: int = 0,
    logger=None,
    use_original_source: bool = False,
) -> bool:
    if inpainter is None:
        if logger is not None:
            logger.info('Batch Re-Inpaint skipped because no inpainter is loaded.')
        return False

    source_img = None
    if not use_original_source:
        source_img = project.load_inpainted_by_imgname(page_name)
    if source_img is None:
        source_img = project.ensure_upscaled_img(page_name)
    if source_img is None:
        if logger is not None:
            logger.info(f'Batch Re-Inpaint skipped {page_name}: source image could not be loaded.')
        return False

    try:
        text_mask = project.load_mask_by_imgname(page_name)
    except Exception:
        if logger is not None:
            logger.warning(f'Could not load stored inpaint mask for {page_name}.', exc_info=True)
        text_mask = None
    try:
        decensor_mask = project.load_decensor_mask_by_imgname(page_name)
    except Exception:
        if logger is not None:
            logger.warning(f'Could not load stored decensor mask for {page_name}.', exc_info=True)
        decensor_mask = None

    mask = combine_inpaint_masks([text_mask, decensor_mask], source_img.shape[:2], dilate=dilate)
    if mask is None or not np.any(mask > 0):
        if logger is not None:
            logger.info(f'Batch Re-Inpaint skipped {page_name}: no saved inpaint masks found.')
        return False

    inpainted = inpainter.inpaint(source_img, mask, project.pages.get(page_name, []))
    project.save_inpainted(page_name, inpainted)
    if page_name == getattr(project, 'current_img', None):
        project.inpainted_array = inpainted
    return True
