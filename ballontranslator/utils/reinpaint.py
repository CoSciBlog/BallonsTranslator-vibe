from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional, Sequence

import cv2
import numpy as np

if TYPE_CHECKING:
    from ballontranslator.modules.inpaint.base import InpainterBase
    from ballontranslator.modules.textdetector.base import TextDetectorBase
    from .proj_imgtrans import ProjImgTrans


def normalize_inpaint_mask(
    mask: Optional[np.ndarray], shape: Sequence[int], dilate: int = 0,
) -> Optional[np.ndarray]:
    """Normalize a saved/detected mask and optionally grow it by a pixel radius.

    >>> normalize_inpaint_mask(np.ones((1, 1), np.uint8), (2, 3)).shape
    (2, 3)
    """
    if type(dilate) is not int or not 0 <= dilate <= 100:
        raise ValueError('Mask expansion must be an integer from 0 to 100.')
    if mask is None:
        return None
    if mask.ndim == 3:
        mask = mask[..., 0]
    mask = (mask > 0).astype(np.uint8) * 255
    height, width = shape[:2]
    if mask.shape != (height, width):
        mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
    if dilate:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (2 * dilate + 1, 2 * dilate + 1),
        )
        mask = cv2.dilate(mask, kernel)
    return mask


def _merge_overlapping_regions(
    regions: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Merge expanded crop rectangles so a mask pixel is inferred only once."""

    merged: list[tuple[int, int, int, int]] = []
    for region in regions:
        x1, y1, x2, y2 = region
        index = 0
        while index < len(merged):
            mx1, my1, mx2, my2 = merged[index]
            if x1 < mx2 and mx1 < x2 and y1 < my2 and my1 < y2:
                x1, y1 = min(x1, mx1), min(y1, my1)
                x2, y2 = max(x2, mx2), max(y2, my2)
                merged.pop(index)
                index = 0
                continue
            index += 1
        merged.append((x1, y1, x2, y2))
    return sorted(merged, key=lambda region: (region[1], region[0]))


def _mask_inpaint_regions(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Build local context crops while keeping nearby glyphs together.

    The saved mask remains unchanged. A temporary dilation is used only to
    group neighbouring character strokes, after which each group receives
    enough surrounding artwork for reconstruction.

    >>> mask = np.zeros((100, 200), np.uint8)
    >>> mask[10:20, 10:20] = mask[70:80, 170:180] = 255
    >>> len(_mask_inpaint_regions(mask))
    2
    """

    height, width = mask.shape[:2]
    join_radius = max(8, min(32, round(min(height, width) * 0.02)))
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * join_radius + 1, 2 * join_radius + 1),
    )
    grouped_mask = cv2.dilate((mask > 0).astype(np.uint8), kernel)
    count, _, stats, _ = cv2.connectedComponentsWithStats(
        grouped_mask, connectivity=8,
    )
    regions: list[tuple[int, int, int, int]] = []
    for label in range(1, count):
        x, y, group_width, group_height, _ = stats[label]
        context = max(24, min(256, round(max(group_width, group_height) * 0.5)))
        regions.append((
            max(0, int(x) - context),
            max(0, int(y) - context),
            min(width, int(x + group_width) + context),
            min(height, int(y + group_height) + context),
        ))
    return _merge_overlapping_regions(regions)


def _inpaint_complete_mask(
    inpainter: InpainterBase,
    image: np.ndarray,
    mask: np.ndarray,
    stop_requested: Optional[Callable[[], bool]],
) -> Optional[np.ndarray]:
    """Inpaint every mask pixel through local, resolution-preserving crops."""

    inpainted = image.copy()
    for x1, y1, x2, y2 in _mask_inpaint_regions(mask):
        if stop_requested is not None and stop_requested():
            return None
        crop = inpainted[y1:y2, x1:x2]
        crop_mask = mask[y1:y2, x1:x2]
        repaired = inpainter.inpaint(crop, crop_mask.copy(), None)
        if repaired.shape != crop.shape:
            raise ValueError(
                'Inpainter returned an image with a different shape for a mask crop.'
            )
        inpainted[y1:y2, x1:x2] = repaired
    return inpainted


def reinpaint_project_page(
    project: Optional[ProjImgTrans],
    inpainter: Optional[InpainterBase],
    page_name: str,
    *,
    allow_maskless: bool = False,
    dilate: int = 0,
    textdetector: Optional[TextDetectorBase] = None,
    stop_requested: Optional[Callable[[], bool]] = None,
) -> bool:
    """Rebuild one inpainted page from its original image and saved mask.

    Each run starts from the original so repeated runs cannot accumulate
    artifacts from an earlier saved result. Saved masks are grouped into local
    context crops independently of existing text regions, so every manual mask
    pixel is retained without downscaling the complete page for one request.
    Optional residual detection repairs the fresh result once more and adds
    missed text to the saved mask, preserving OCR and translations.
    The expanded/combined mask is saved only after inference succeeds.
    ``False`` means there was no reusable input or cancellation was requested.

    >>> reinpaint_project_page(None, None, '001.png')
    False
    """

    if project is None or inpainter is None or page_name not in project.pages:
        return False
    if stop_requested is not None and stop_requested():
        return False

    source_image = project.read_img(page_name)
    saved_mask = project.load_mask_by_imgname(page_name)
    mask = normalize_inpaint_mask(saved_mask, source_image.shape, dilate)
    blocks = project.pages.get(page_name, [])
    has_mask = mask is not None and bool(np.any(mask > 0))
    if not has_mask and not (allow_maskless and blocks):
        return False

    # Passing text blocks makes block-based inpainters discard mask pixels
    # outside their OCR-derived crops. Local crops retain every saved mask
    # pixel while avoiding a resolution-losing full-page model invocation.
    if has_mask:
        inpainted = _inpaint_complete_mask(
            inpainter, source_image, mask, stop_requested,
        )
        if inpainted is None:
            return False
    else:
        inpainted = inpainter.inpaint(source_image, None, blocks)
    if stop_requested is not None and stop_requested():
        return False
    if textdetector is not None:
        residual, _ = textdetector.detect(inpainted, project)
        if stop_requested is not None and stop_requested():
            return False
        residual = normalize_inpaint_mask(residual, source_image.shape, dilate)
        if residual is not None and np.any(residual):
            mask = residual if mask is None else cv2.bitwise_or(mask, residual)
            # Repair the fresh result so text inside the original mask can
            # improve too, rather than repeating identical inference on source.
            # Keep the complete residual mask, including pixels outside OCR crops.
            repaired = _inpaint_complete_mask(
                inpainter, inpainted, residual, stop_requested,
            )
            if repaired is None:
                return False
            inpainted = repaired
    if stop_requested is not None and stop_requested():
        return False
    project.save_inpainted(page_name, inpainted)
    if mask is not None and not np.array_equal(mask, saved_mask):
        project.save_mask(page_name, mask)
    if page_name == getattr(project, 'current_img', None):
        project.inpainted_array = inpainted
        if mask is not None:
            project.mask_array = mask
    return True
