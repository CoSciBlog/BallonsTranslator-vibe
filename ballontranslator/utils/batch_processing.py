from __future__ import annotations

import os
import os.path as osp
from dataclasses import dataclass
from typing import Iterable, List

from natsort import natsorted

from .io_utils import find_all_imgs


ORDER_PROJECT = 'project'
ORDER_STAGED = 'staged'

GLOSSARY_INDIVIDUAL = 'individual'
GLOSSARY_GLOBAL = 'global'

COMPLETION_NONE = 'none'
COMPLETION_HIBERNATE = 'hibernate'
COMPLETION_SHUTDOWN = 'shutdown'
COMPLETION_RESTART = 'restart'
COMPLETION_CLOSE = 'close'

_GENERATED_DIRECTORIES = {
    'mask', 'result', 'inpainted', 'upscaled', 'decensor_mask', 'decensored',
}


@dataclass(frozen=True)
class BatchOptions:
    root_directory: str
    textdetector: str
    ocr: str
    fallback_ocr: str
    inpainter: str
    translator: str
    enable_detect: bool = True
    enable_ocr: bool = True
    enable_inpaint: bool = True
    enable_translate: bool = True
    glossary_mode: str = GLOSSARY_INDIVIDUAL
    upscale_first: bool = False
    rerun_inpaint: bool = False
    order: str = ORDER_PROJECT
    completion_action: str = COMPLETION_NONE


@dataclass(frozen=True)
class BatchTask:
    project_directory: str
    phase: str
    enable_detect: bool
    enable_ocr: bool
    enable_inpaint: bool
    enable_translate: bool
    upscale_first: bool = False
    rerun_inpaint: bool = False


def collect_batch_project_dirs(root_directory: str) -> List[str]:
    """Return image-bearing direct child folders in deterministic order.

    The selected root is deliberately not treated as a project. This keeps a
    batch bounded to the direct children visible to the user.

    >>> collect_batch_project_dirs('')
    []
    """

    if not root_directory or not osp.isdir(root_directory):
        return []
    projects = []
    try:
        entries = list(os.scandir(root_directory))
    except OSError:
        return []
    for entry in entries:
        if (
            not entry.is_dir(follow_symlinks=False)
            or entry.name.casefold() in _GENERATED_DIRECTORIES
        ):
            continue
        try:
            if find_all_imgs(entry.path):
                projects.append(osp.abspath(entry.path))
        except OSError:
            continue
    return natsorted(projects)


def build_batch_tasks(
    project_directories: Iterable[str],
    options: BatchOptions,
) -> List[BatchTask]:
    """Build the execution plan without loading projects or models.

    >>> opts = BatchOptions('root', 'det', 'ocr', '', 'paint', 'trans')
    >>> [task.phase for task in build_batch_tasks(['a', 'b'], opts)]
    ['complete', 'complete']
    >>> staged = BatchOptions('root', 'det', 'ocr', '', 'paint', 'trans', order='staged')
    >>> [task.phase for task in build_batch_tasks(['a', 'b'], staged)]
    ['local', 'local', 'translation', 'translation']
    """

    projects = list(project_directories)
    if options.order != ORDER_STAGED:
        return [
            BatchTask(
                directory,
                'complete',
                options.enable_detect,
                options.enable_ocr,
                options.enable_inpaint,
                options.enable_translate,
                options.upscale_first,
                options.rerun_inpaint,
            )
            for directory in projects
        ]

    tasks: List[BatchTask] = []
    local_enabled = (
        options.enable_detect
        or options.enable_ocr
        or options.enable_inpaint
        or options.rerun_inpaint
    )
    if local_enabled:
        tasks.extend(
            BatchTask(
                directory,
                'local',
                options.enable_detect,
                options.enable_ocr,
                options.enable_inpaint,
                False,
                options.upscale_first,
                options.rerun_inpaint,
            )
            for directory in projects
        )
    if options.enable_translate:
        tasks.extend(
            BatchTask(
                directory,
                'translation',
                False,
                False,
                False,
                True,
                options.upscale_first and not local_enabled,
                False,
            )
            for directory in projects
        )
    return tasks


def windows_completion_command(action: str) -> List[str]:
    """Return the Windows power command for a successful batch."""

    commands = {
        COMPLETION_HIBERNATE: ['shutdown', '/h'],
        COMPLETION_SHUTDOWN: ['shutdown', '/s', '/t', '0'],
        COMPLETION_RESTART: ['shutdown', '/r', '/t', '0'],
    }
    return list(commands.get(action, ()))
