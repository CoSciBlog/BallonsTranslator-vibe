import os
import os.path as osp
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


def collect_batch_project_dirs(root_dir: str) -> List[str]:
    """Return immediate child folders that can be processed as projects."""
    if not root_dir or not osp.isdir(root_dir):
        return []

    project_dirs = []
    for name in natsorted(os.listdir(root_dir)):
        path = osp.join(root_dir, name)
        if not osp.isdir(path):
            continue
        if name.lower() in IGNORED_BATCH_DIRS:
            continue
        if find_all_imgs(path, abs_path=False, sort=False):
            project_dirs.append(path)
    return project_dirs
