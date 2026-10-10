import os
import os.path as osp
import re
import shutil
import tempfile
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from .io_utils import IMG_EXT, imread, imwrite
from .logger import logger as LOGGER


_UPSCALE_SUFFIX_RE = re.compile(
    r'(?i)(?:_x(?P<current>\d+)|_upscaled_(?P<legacy>\d+)x)$'
)


def upscaled_page_name(page_name: str, factor: int) -> str:
    """Return the page name carrying its cumulative upscale factor.

    >>> upscaled_page_name('001.png', 2)
    '001_x2.png'
    >>> upscaled_page_name('001_x2.png', 2)
    '001_x4.png'
    >>> upscaled_page_name('001_upscaled_2x.png', 3)
    '001_x6.png'
    """
    if isinstance(factor, bool) or not isinstance(factor, int) or factor < 2:
        raise ValueError('The upscale factor must be an integer of at least 2.')
    stem, extension = osp.splitext(page_name)
    match = _UPSCALE_SUFFIX_RE.search(stem)
    previous_factor = 1
    if match is not None:
        previous_factor = int(match.group('current') or match.group('legacy'))
        stem = stem[:match.start()]
    return f'{stem}_x{previous_factor * factor}{extension}'


def upscale_image(image: np.ndarray, factor: int = 2) -> np.ndarray:
    """Enlarge an image by an integer factor using sharpened cubic sampling.

    >>> upscale_image(np.zeros((2, 3, 3), dtype=np.uint8), 3).shape
    (6, 9, 3)
    """
    if isinstance(factor, bool) or not isinstance(factor, int) or factor < 2:
        raise ValueError('The upscale factor must be an integer of at least 2.')
    if image is None or image.ndim < 2:
        raise ValueError('A valid image is required for upscaling.')
    height, width = image.shape[:2]
    enlarged = cv2.resize(
        image,
        (width * factor, height * factor),
        interpolation=cv2.INTER_CUBIC,
    )
    blurred = cv2.GaussianBlur(enlarged, (0, 0), sigmaX=0.8)
    return cv2.addWeighted(enlarged, 1.18, blurred, -0.18, 0)


def upscale_image_2x(image: np.ndarray) -> np.ndarray:
    """Enlarge an image by exactly two.

    >>> upscale_image_2x(np.zeros((2, 3, 3), dtype=np.uint8)).shape
    (4, 6, 3)
    """
    return upscale_image(image, 2)


def stage_upscaled_pages(
    directory: str,
    page_names: List[str],
    *,
    factor: int = 2,
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
            output = upscale_image(image, factor)
            target_name = upscaled_page_name(page_name, factor)
            staged_path = osp.join(staging_dir, target_name)
            os.makedirs(osp.dirname(staged_path), exist_ok=True)
            imwrite(staged_path, output, ext=extension, quality=100)
            out_height, out_width = output.shape[:2]
            source_height, source_width = image.shape[:2]
            replacements.append({
                'source_name': page_name,
                'target_name': target_name,
                'staged_path': staged_path,
                'factor': float(factor),
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
