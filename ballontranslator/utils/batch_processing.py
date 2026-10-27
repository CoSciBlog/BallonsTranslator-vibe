from __future__ import annotations

import json
import os
import os.path as osp
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from natsort import natsorted

from .io_utils import find_all_imgs
from .logger import logger as LOGGER


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

BATCH_RESUME_FILENAME = '.ballontranslator_batch_resume.json'
BATCH_RESUME_SCHEMA_VERSION = 1


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
    resume: bool = True
    translator_llm_id: str = ''


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


def _canonical_path(path: str) -> str:
    return osp.normcase(osp.abspath(path))


def batch_task_key(task: BatchTask) -> str:
    """Return a stable key for one task in an exact batch plan."""

    return json.dumps(
        [_canonical_path(task.project_directory), task.phase],
        ensure_ascii=False,
        separators=(',', ':'),
    )


def batch_resume_plan(
    options: BatchOptions,
    project_directories: Iterable[str],
    tasks: Iterable[BatchTask],
) -> Dict[str, Any]:
    """Describe work whose completed tasks may safely be reused.

    UI-only choices such as the completion action are deliberately excluded.
    Changing a module, stage, order, glossary scope, or project list starts a
    different plan instead of borrowing unrelated completion state.
    """

    return {
        'root_directory': _canonical_path(options.root_directory),
        'project_directories': [
            _canonical_path(directory) for directory in project_directories
        ],
        'pipeline': {
            'textdetector': options.textdetector,
            'ocr': options.ocr,
            'fallback_ocr': options.fallback_ocr,
            'inpainter': options.inpainter,
            'translator': options.translator,
            'translator_llm_id': options.translator_llm_id,
            'enable_detect': options.enable_detect,
            'enable_ocr': options.enable_ocr,
            'enable_inpaint': options.enable_inpaint,
            'enable_translate': options.enable_translate,
            'glossary_mode': options.glossary_mode,
            'upscale_first': options.upscale_first,
            'rerun_inpaint': options.rerun_inpaint,
            'order': options.order,
        },
        'tasks': [batch_task_key(task) for task in tasks],
    }


class BatchResumeStore:
    """Atomically persist completed tasks for one interrupted batch plan.

    >>> BatchResumeStore.filename
    '.ballontranslator_batch_resume.json'
    """

    filename = BATCH_RESUME_FILENAME

    def __init__(self, root_directory: str) -> None:
        self.path = Path(root_directory).resolve() / self.filename

    def prepare(self, plan: Dict[str, Any], *, resume: bool) -> Set[str]:
        completed: Set[str] = set()
        if resume and self.path.is_file():
            try:
                payload = self._load()
                valid_keys = set(plan['tasks'])
                saved = payload.get('completed_tasks')
                if payload.get('plan') == plan and isinstance(saved, list):
                    completed = {
                        key for key in saved
                        if isinstance(key, str) and key in valid_keys
                    }
                    if len(completed) != len(saved):
                        LOGGER.warning(
                            'Discarded invalid entries from the batch resume checkpoint.'
                        )
                elif payload.get('plan') != plan:
                    LOGGER.info(
                        'The saved batch resume checkpoint belongs to a different plan.'
                    )
                else:
                    LOGGER.warning(
                        'Discarded malformed completed_tasks from the batch resume checkpoint.'
                    )
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                LOGGER.warning('Discarded invalid batch resume checkpoint: %s', error)
        self._save(plan, completed)
        return completed

    def mark_completed(self, plan: Dict[str, Any], task_key: str) -> None:
        completed = self._load_progress(plan, task_key)
        completed.add(task_key)
        self._save(plan, completed)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _load(self) -> Dict[str, Any]:
        with self.path.open('r', encoding='utf-8') as checkpoint_file:
            payload = json.load(checkpoint_file)
        if (
            not isinstance(payload, dict)
            or payload.get('schema_version') != BATCH_RESUME_SCHEMA_VERSION
            or not isinstance(payload.get('plan'), dict)
        ):
            raise ValueError('Unsupported or malformed batch resume checkpoint.')
        return payload

    def _load_progress(
        self,
        plan: Dict[str, Any],
        task_key: str,
    ) -> Set[str]:
        valid_keys = set(plan['tasks'])
        if task_key not in valid_keys:
            raise ValueError('Task does not belong to the active batch plan.')
        completed: Set[str] = set()
        if self.path.is_file():
            try:
                payload = self._load()
                if payload.get('plan') == plan:
                    completed_payload = payload.get('completed_tasks', [])
                    if isinstance(completed_payload, list):
                        completed = {
                            key for key in completed_payload
                            if isinstance(key, str) and key in valid_keys
                        }
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                LOGGER.warning(
                    'Rebuilding invalid batch resume checkpoint: %s', error
                )
        return completed

    def _save(
        self,
        plan: Dict[str, Any],
        completed: Set[str],
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix='.batch_resume.', suffix='.tmp', dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as output:
                json.dump(
                    {
                        'schema_version': BATCH_RESUME_SCHEMA_VERSION,
                        'plan': plan,
                        'completed_tasks': sorted(completed),
                    },
                    output,
                    ensure_ascii=False,
                    indent=2,
                )
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if osp.exists(temporary_path):
                os.unlink(temporary_path)


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
    >>> upscaled = BatchOptions('root', 'det', 'ocr', '', 'paint', 'trans', upscale_first=True)
    >>> [task.phase for task in build_batch_tasks(['a', 'b'], upscaled)]
    ['upscale', 'upscale', 'complete', 'complete']
    >>> only_upscale = BatchOptions(
    ...     'root', 'det', 'ocr', '', 'paint', 'trans',
    ...     enable_detect=False, enable_ocr=False, enable_inpaint=False,
    ...     enable_translate=False, upscale_first=True,
    ... )
    >>> [task.phase for task in build_batch_tasks(['a', 'b'], only_upscale)]
    ['upscale', 'upscale']
    >>> staged = BatchOptions('root', 'det', 'ocr', '', 'paint', 'trans', order='staged')
    >>> [task.phase for task in build_batch_tasks(['a', 'b'], staged)]
    ['local', 'local', 'translation', 'translation']
    """

    projects = list(project_directories)
    tasks: List[BatchTask] = []
    if options.upscale_first:
        # This is a batch-wide prerequisite: no project's pipeline may start
        # until every selected project has finished upscaling.
        tasks.extend(
            BatchTask(
                directory,
                'upscale',
                False,
                False,
                False,
                False,
                True,
                False,
            )
            for directory in projects
        )

    pipeline_enabled = any((
        options.enable_detect,
        options.enable_ocr,
        options.enable_inpaint,
        options.enable_translate,
        options.rerun_inpaint,
    ))
    if not pipeline_enabled:
        return tasks

    if options.order != ORDER_STAGED:
        tasks.extend(
            BatchTask(
                directory,
                'complete',
                options.enable_detect,
                options.enable_ocr,
                options.enable_inpaint,
                options.enable_translate,
                False,
                options.rerun_inpaint,
            )
            for directory in projects
        )
        return tasks

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
                False,
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
                False,
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
