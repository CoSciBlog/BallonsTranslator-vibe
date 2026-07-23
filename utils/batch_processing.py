import os
import os.path as osp
import re
from typing import Dict, List, Set

from natsort import natsorted

from .glossary_replacement import parse_preferred_targets, render_preferred_target
from .glossary_template import merge_glossary_entry_text
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


def merge_batch_glossaries(
    shared_glossary: Dict[str, str],
    project_glossary: Dict[str, str],
    default_glossary: Dict[str, str] = None,
) -> Dict[str, str]:
    """Merge a cumulative batch glossary into a project's local glossary.

    Project entries are ordered first and therefore win when the same source and
    category already exist in the cumulative glossary. Custom project prompts
    override shared prompts, while untouched default prompts keep the shared
    batch value.
    """
    shared = dict(shared_glossary or {})
    project = dict(project_glossary or {})
    defaults = dict(default_glossary or {})
    merged = dict(shared)

    for field in ('entries', 'reference_entries'):
        merged[field] = merge_glossary_entry_text(
            project.get(field, ''),
            shared.get(field, ''),
        )

    merged['preferred_targets'] = _merge_preferred_targets(
        project.get('preferred_targets', ''),
        shared.get('preferred_targets', ''),
    )

    for field in ('prompt', 'reference_prompt'):
        project_value = project.get(field, '')
        default_value = defaults.get(field, '')
        if project_value and project_value != default_value:
            merged[field] = project_value
        elif shared.get(field):
            merged[field] = shared[field]
        else:
            merged[field] = project_value or default_value

    return merged


def _merge_preferred_targets(project_text: str, shared_text: str) -> str:
    lines = []
    seen = set()
    for text in (project_text, shared_text):
        for entry in parse_preferred_targets(text):
            key = (
                entry.get('target', '').strip().casefold(),
                entry.get('category', '').strip().casefold(),
            )
            if not key[0] or key in seen:
                continue
            lines.append(render_preferred_target(entry))
            seen.add(key)
    return '\n'.join(lines)
