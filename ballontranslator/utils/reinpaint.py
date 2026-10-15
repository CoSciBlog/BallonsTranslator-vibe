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
    artifacts from an earlier saved result. Saved masks are applied as
    complete page masks rather than being cropped again by existing text
    regions. Optional residual detection repairs the fresh result once more
    and adds missed text to the saved mask, preserving OCR and translations.
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
    # outside their OCR-derived crops. Re-inpainting must consume every saved
    # mask pixel, including manual mask extensions and missed glyph edges.
    inpainted = inpainter.inpaint(
        source_image,
        mask.copy() if mask is not None else None,
        None if has_mask else blocks,
    )
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
            inpainted = inpainter.inpaint(inpainted, residual.copy(), None)
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
