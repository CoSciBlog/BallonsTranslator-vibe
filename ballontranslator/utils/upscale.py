import os
import os.path as osp
import shutil
import tempfile
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from .io_utils import IMG_EXT, imread, imwrite
from .logger import logger as LOGGER


def upscale_image_2x(image: np.ndarray) -> np.ndarray:
    """Enlarge an image by exactly two using sharpened cubic sampling.

    >>> upscale_image_2x(np.zeros((2, 3, 3), dtype=np.uint8)).shape
    (4, 6, 3)
    """
    if image is None or image.ndim < 2:
        raise ValueError('A valid image is required for upscaling.')
    height, width = image.shape[:2]
    enlarged = cv2.resize(
        image,
        (width * 2, height * 2),
        interpolation=cv2.INTER_CUBIC,
    )
    blurred = cv2.GaussianBlur(enlarged, (0, 0), sigmaX=0.8)
    return cv2.addWeighted(enlarged, 1.18, blurred, -0.18, 0)


def stage_upscaled_pages(
    directory: str,
    page_names: List[str],
    *,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    stop_requested: Optional[Callable[[], bool]] = None,
) -> Tuple[List[Dict], List[Tuple[str, str]], bool, str]:
    """Generate every replacement before any original image is touched."""
    staging_dir = tempfile.mkdtemp(prefix='.upscale_staging_', dir=directory)
    replacements: List[Dict] = []
    failures: List[Tuple[str, str]] = []
    total = len(page_names)

    for current, page_name in enumerate(page_names, start=1):
        if stop_requested is not None and stop_requested():
            shutil.rmtree(staging_dir, ignore_errors=True)
            return [], failures, True, ''
        try:
            extension = osp.splitext(page_name)[1].lower()
            if extension not in IMG_EXT:
                raise ValueError(f'Unsupported image extension: {extension}')
            source_path = osp.join(directory, page_name)
            image = imread(source_path)
            output = upscale_image_2x(image)
            staged_path = osp.join(staging_dir, page_name)
            os.makedirs(osp.dirname(staged_path), exist_ok=True)
            imwrite(staged_path, output, ext=extension, quality=100)
            out_height, out_width = output.shape[:2]
            source_height, source_width = image.shape[:2]
            replacements.append({
                'source_name': page_name,
                'staged_path': staged_path,
                'factor': 2.0,
                'width': out_width,
                'height': out_height,
                'original_width': source_width,
                'original_height': source_height,
            })
        except Exception as error:
            LOGGER.exception('Failed to upscale project image %s.', page_name)
            failures.append((page_name, str(error)))
        finally:
            if progress_callback is not None:
                progress_callback(current, total)

    if stop_requested is not None and stop_requested():
        shutil.rmtree(staging_dir, ignore_errors=True)
        return [], failures, True, ''
    if failures:
        shutil.rmtree(staging_dir, ignore_errors=True)
        return [], failures, False, ''
    return replacements, failures, False, staging_dir
