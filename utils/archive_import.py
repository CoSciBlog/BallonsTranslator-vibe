import json
import os
import os.path as osp
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, List

from natsort import natsorted

from .io_utils import IMG_EXT
from .logger import logger as LOGGER


ARCHIVE_EXT = {'.zip', '.cbz', '.cbr'}
IMPORT_METADATA = 'archive_import.json'


class ArchiveImportError(Exception):
    pass


def is_archive_path(path: str) -> bool:
    return Path(path).suffix.lower() in ARCHIVE_EXT


def archive_filter() -> str:
    return 'Comic archives (*.cbz *.cbr *.zip)'


def _safe_project_dir_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', name).strip(' ._')
    return cleaned or 'archive_project'


def archive_project_dir(archive_path: str) -> str:
    archive = Path(archive_path)
    return str(archive.with_name(_safe_project_dir_name(archive.stem)))


def _is_supported_image_name(name: str) -> bool:
    path = Path(name)
    if path.name.startswith('.') or any(part.startswith('__MACOSX') for part in path.parts):
        return False
    return path.suffix.lower() in IMG_EXT


def _safe_image_name(index: int, source_name: str, used_names: set) -> str:
    source = Path(source_name)
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', source.stem).strip(' ._') or 'page'
    ext = source.suffix.lower()
    candidate = f'{index:04d}_{stem}{ext}'
    suffix = 1
    while candidate.lower() in used_names:
        candidate = f'{index:04d}_{stem}_{suffix}{ext}'
        suffix += 1
    used_names.add(candidate.lower())
    return candidate


def _prepare_destination(archive_path: str) -> str:
    dest_dir = archive_project_dir(archive_path)
    if osp.isdir(dest_dir):
        existing_imgs = [p for p in os.listdir(dest_dir) if _is_supported_image_name(p)]
        if existing_imgs:
            LOGGER.info(f'Using existing archive import folder: {dest_dir}')
            return dest_dir
        if os.listdir(dest_dir):
            raise ArchiveImportError(
                f'Cannot import archive into non-empty folder without images: {dest_dir}'
            )
    else:
        os.makedirs(dest_dir)
    return dest_dir


def _write_metadata(dest_dir: str, archive_path: str, image_names: List[str]) -> None:
    stat = os.stat(archive_path)
    metadata = {
        'source_archive': osp.abspath(archive_path),
        'source_size': stat.st_size,
        'source_mtime': stat.st_mtime,
        'image_count': len(image_names),
        'images': image_names,
    }
    with open(osp.join(dest_dir, IMPORT_METADATA), 'w', encoding='utf8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def _import_zip_archive(archive_path: str, dest_dir: str) -> List[str]:
    image_members = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if _is_supported_image_name(info.filename):
                image_members.append(info)
        image_members = natsorted(image_members, key=lambda item: item.filename)

        used_names = set()
        written = []
        for index, info in enumerate(image_members, start=1):
            image_name = _safe_image_name(index, info.filename, used_names)
            target = osp.join(dest_dir, image_name)
            with archive.open(info) as src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            written.append(image_name)
    return written


def _seven_zip_command() -> str:
    for candidate in ('7z', '7zz', '7za'):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise ArchiveImportError(
        'CBR import requires a 7z-compatible extractor on PATH. '
        'Install 7-Zip or run inside the Pinokio environment that provides 7z.'
    )


def _iter_images_recursive(root: str) -> Iterable[str]:
    for current_root, _, files in os.walk(root):
        for filename in files:
            path = osp.join(current_root, filename)
            rel = osp.relpath(path, root)
            if _is_supported_image_name(rel):
                yield path


def _import_cbr_archive(archive_path: str, dest_dir: str) -> List[str]:
    seven_zip = _seven_zip_command()
    with tempfile.TemporaryDirectory(prefix='btrans_cbr_') as tmpdir:
        result = subprocess.run(
            [seven_zip, 'x', '-y', f'-o{tmpdir}', archive_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ArchiveImportError(
                'Failed to extract CBR archive with 7z.\n'
                f'stdout:\n{result.stdout}\n'
                f'stderr:\n{result.stderr}'
            )

        image_paths = natsorted(_iter_images_recursive(tmpdir), key=lambda p: osp.relpath(p, tmpdir))
        used_names = set()
        written = []
        for index, image_path in enumerate(image_paths, start=1):
            rel_name = osp.relpath(image_path, tmpdir)
            image_name = _safe_image_name(index, rel_name, used_names)
            shutil.copy2(image_path, osp.join(dest_dir, image_name))
            written.append(image_name)
    return written


def import_archive_to_project(archive_path: str) -> str:
    if not osp.isfile(archive_path):
        raise ArchiveImportError(f'Archive file does not exist: {archive_path}')
    ext = Path(archive_path).suffix.lower()
    if ext not in ARCHIVE_EXT:
        raise ArchiveImportError(f'Unsupported archive extension: {ext}')

    dest_dir = _prepare_destination(archive_path)
    if [p for p in os.listdir(dest_dir) if _is_supported_image_name(p)]:
        return dest_dir

    LOGGER.info(f'Importing archive {archive_path} into {dest_dir}')
    if ext in {'.zip', '.cbz'}:
        image_names = _import_zip_archive(archive_path, dest_dir)
    elif ext == '.cbr':
        image_names = _import_cbr_archive(archive_path, dest_dir)
    else:
        image_names = []

    if not image_names:
        raise ArchiveImportError(f'Archive contains no supported image files: {archive_path}')

    _write_metadata(dest_dir, archive_path, image_names)
    return dest_dir
