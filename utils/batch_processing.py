import os
import os.path as osp
import re
from typing import List, Set

from natsort import natsorted

from .io_utils import find_all_imgs


IGNORED_BATCH_DIRS: Set[str] = {
    'mask',
    'result',
    'inpainted',
    'upscaled',
    'decensor_mask',
    'decensored',
}


def parse_batch_paths(path_text: str) -> List[str]:
    """Split semicolon/newline separated batch inputs while retaining order."""
    paths = []
    seen = set()
    for value in re.split(r'[;\r\n]+', path_text or ''):
        path = value.strip().strip('"')
        if not path:
            continue
        path = osp.normpath(path)
        key = osp.normcase(osp.abspath(path))
        if key not in seen:
            paths.append(path)
            seen.add(key)
    return paths


def collect_batch_project_dirs(root_dir: str) -> List[str]:
    """Return image project folders selected directly or beneath entered roots."""
    project_dirs = []
    seen = set()
    for root in parse_batch_paths(root_dir):
        if not osp.isdir(root):
            continue

        candidates = []
        if osp.basename(root).lower() not in IGNORED_BATCH_DIRS and find_all_imgs(root, abs_path=False, sort=False):
            candidates.append(root)
        for name in natsorted(os.listdir(root)):
            path = osp.join(root, name)
            if not osp.isdir(path) or name.lower() in IGNORED_BATCH_DIRS:
                continue
            if find_all_imgs(path, abs_path=False, sort=False):
                candidates.append(path)

        for path in candidates:
            key = osp.normcase(osp.abspath(path))
            if key not in seen:
                project_dirs.append(path)
                seen.add(key)
    return project_dirs
