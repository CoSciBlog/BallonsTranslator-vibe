from __future__ import annotations

from typing import Optional

import numpy as np


def reinpaint_project_page(
    project,
    inpainter,
    page_name: str,
    *,
    allow_maskless: bool = False,
) -> bool:
    """Rebuild one inpainted page from its original image and saved mask.

    The original source is always used so repeated runs cannot accumulate
    artifacts from an earlier inpainting result.  ``False`` means that the
    page had no reusable mask (or, for a maskless inpainter, no text blocks).

    >>> reinpaint_project_page(None, None, '001.png')
    False
    """

    if project is None or inpainter is None or page_name not in project.pages:
        return False

    source_image = project.read_img(page_name)
    mask: Optional[np.ndarray] = project.load_mask_by_imgname(page_name)
    blocks = project.pages.get(page_name, [])
    has_mask = mask is not None and bool(np.any(mask > 0))
    if not has_mask and not (allow_maskless and blocks):
        return False

    inpainted = inpainter.inpaint(source_image, mask, blocks)
    project.save_inpainted(page_name, inpainted)
    if page_name == getattr(project, 'current_img', None):
        project.inpainted_array = inpainted
    return True
