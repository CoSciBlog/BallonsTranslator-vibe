import json
import os
import os.path as osp
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, List, Sequence

from natsort import natsorted

from .io_utils import IMG_EXT
from .logger import logger as LOGGER


ARCHIVE_EXT = {'.zip', '.cbz', '.cbr', '.pdf'}
IMPORT_METADATA = 'archive_import.json'
IMPORT_EXCLUDE_DIRS = {
    'mask',
    'inpainted',
    'result',
    'upscaled',
    'decensor_mask',
    'decensored',
    '__pycache__',
}


class ArchiveImportError(Exception):
    pass


def is_archive_path(path: str) -> bool:
    return Path(path).suffix.lower() in ARCHIVE_EXT


def is_importable_file_path(path: str) -> bool:
    return Path(path).suffix.lower() in set(ARCHIVE_EXT).union(IMG_EXT)


def archive_filter() -> str:
    return 'Comic archives and PDFs (*.cbz *.cbr *.zip *.pdf)'


def _safe_project_dir_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', name).strip(' ._')
    return cleaned or 'archive_project'


def archive_project_dir(archive_path: str) -> str:
    archive = Path(archive_path)
    return str(archive.with_name(_safe_project_dir_name(archive.stem)))


def multi_pdf_project_dir(pdf_paths: List[str]) -> str:
    first_pdf = Path(pdf_paths[0])
    return str(first_pdf.with_name(_safe_project_dir_name(first_pdf.stem + '_pdf_import')))


def source_collection_project_dir(source_paths: Sequence[str]) -> str:
    first_source = Path(source_paths[0])
    if first_source.is_dir():
        return str(first_source.with_name(_safe_project_dir_name(first_source.name + '_import')))
    return str(first_source.with_name(_safe_project_dir_name(first_source.stem + '_import')))


def _is_supported_image_name(name: str) -> bool:
    path = Path(name)
    if path.name.startswith('.') or any(part.startswith('__MACOSX') for part in path.parts):
        return False
    return path.suffix.lower() in IMG_EXT


def _is_excluded_dir(path: str) -> bool:
    path_obj = Path(path)
    return any(part in IMPORT_EXCLUDE_DIRS or part.startswith('.') for part in path_obj.parts)


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


def _group_name(path: str) -> str:
    return Path(path).stem if osp.isfile(path) else Path(path).name


def _source_type(path: str) -> str:
    if osp.isdir(path):
        return 'folder'
    ext = Path(path).suffix.lower()
    if ext == '.pdf':
        return 'pdf'
    if ext in {'.zip', '.cbz', '.cbr'}:
        return 'archive'
    if ext in IMG_EXT:
        return 'image'
    return 'file'


def _image_group_for_collection(image_path: str, source_paths: Sequence[str]) -> str:
    image_path = osp.abspath(image_path)
    directory_roots = [osp.abspath(path) for path in source_paths if osp.isdir(path)]
    directory_roots = sorted(directory_roots, key=len, reverse=True)
    for root in directory_roots:
        try:
            rel = osp.relpath(image_path, root)
        except ValueError:
            continue
        if rel.startswith('..'):
            continue
        parent = osp.dirname(rel)
        if parent in {'', '.'}:
            return Path(root).name
        return (Path(Path(root).name) / Path(parent)).as_posix()
    return Path(image_path).parent.name or Path(image_path).stem


def _source_name_for_collection(image_path: str, source_paths: Sequence[str]) -> str:
    image_path = osp.abspath(image_path)
    directory_roots = [osp.abspath(path) for path in source_paths if osp.isdir(path)]
    directory_roots = sorted(directory_roots, key=len, reverse=True)
    for root in directory_roots:
        try:
            rel = osp.relpath(image_path, root)
        except ValueError:
            continue
        if not rel.startswith('..'):
            return rel
    return image_path


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
    group = _group_name(archive_path)
    metadata = {
        'source_archive': osp.abspath(archive_path),
        'source_size': stat.st_size,
        'source_mtime': stat.st_mtime,
        'image_count': len(image_names),
        'images': image_names,
        'image_groups': [{
            'name': group,
            'type': _source_type(archive_path),
            'source': osp.abspath(archive_path),
            'images': image_names,
        }],
    }
    with open(osp.join(dest_dir, IMPORT_METADATA), 'w', encoding='utf8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def _write_multi_pdf_metadata(dest_dir: str, pdf_paths: List[str], image_names: List[str], image_groups: List[dict] = None) -> None:
    sources = []
    for pdf_path in pdf_paths:
        stat = os.stat(pdf_path)
        sources.append({
            'source_pdf': osp.abspath(pdf_path),
            'source_size': stat.st_size,
            'source_mtime': stat.st_mtime,
        })
    metadata = {
        'source_pdfs': sources,
        'image_count': len(image_names),
        'images': image_names,
        'image_groups': image_groups or [],
    }
    with open(osp.join(dest_dir, IMPORT_METADATA), 'w', encoding='utf8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def _write_collection_metadata(dest_dir: str, source_paths: Sequence[str], image_names: List[str], image_groups: List[dict]) -> None:
    sources = []
    for source_path in source_paths:
        source = {
            'path': osp.abspath(source_path),
            'type': _source_type(source_path),
        }
        if osp.isfile(source_path):
            stat = os.stat(source_path)
            source.update({
                'source_size': stat.st_size,
                'source_mtime': stat.st_mtime,
            })
        sources.append(source)
    metadata = {
        'source_collection': sources,
        'image_count': len(image_names),
        'images': image_names,
        'image_groups': image_groups,
    }
    with open(osp.join(dest_dir, IMPORT_METADATA), 'w', encoding='utf8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def _import_zip_archive(archive_path: str, dest_dir: str, used_names: set = None, start_index: int = 1) -> List[str]:
    image_members = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if _is_supported_image_name(info.filename):
                image_members.append(info)
        image_members = natsorted(image_members, key=lambda item: item.filename)

        if used_names is None:
            used_names = set()
        written = []
        for index, info in enumerate(image_members, start=start_index):
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
        if _is_excluded_dir(osp.relpath(current_root, root)):
            continue
        for filename in files:
            path = osp.join(current_root, filename)
            rel = osp.relpath(path, root)
            if _is_supported_image_name(rel):
                yield path


def _import_cbr_archive(archive_path: str, dest_dir: str, used_names: set = None, start_index: int = 1) -> List[str]:
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
        if used_names is None:
            used_names = set()
        written = []
        for index, image_path in enumerate(image_paths, start=start_index):
            rel_name = osp.relpath(image_path, tmpdir)
            image_name = _safe_image_name(index, rel_name, used_names)
            shutil.copy2(image_path, osp.join(dest_dir, image_name))
            written.append(image_name)
    return written


def _render_pdf_pages(pdf_path: str, dest_dir: str, used_names: set, start_index: int) -> List[str]:
    try:
        import fitz
    except ImportError as e:
        raise ArchiveImportError(
            'PDF import requires PyMuPDF. Run the launcher update/install step to install it.'
        ) from e

    written = []
    document = fitz.open(pdf_path)
    try:
        if document.page_count == 0:
            raise ArchiveImportError(f'PDF contains no pages: {pdf_path}')

        zoom = 2.0
        matrix = fitz.Matrix(zoom, zoom)
        source_stem = Path(pdf_path).stem
        for page_number in range(document.page_count):
            page = document.load_page(page_number)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            source_name = f'{source_stem}_page_{page_number + 1:04d}.png'
            image_name = _safe_image_name(start_index + len(written), source_name, used_names)
            pixmap.save(osp.join(dest_dir, image_name))
            written.append(image_name)
    finally:
        document.close()
    return written


def _import_pdf(pdf_path: str, dest_dir: str) -> List[str]:
    return _render_pdf_pages(pdf_path, dest_dir, set(), 1)


def _copy_image_file(image_path: str, dest_dir: str, used_names: set, index: int, source_name: str = None) -> str:
    image_name = _safe_image_name(index, source_name or image_path, used_names)
    shutil.copy2(image_path, osp.join(dest_dir, image_name))
    return image_name


def _prepare_multi_pdf_destination(pdf_paths: List[str]) -> str:
    dest_dir = multi_pdf_project_dir(pdf_paths)
    if osp.isdir(dest_dir):
        existing_imgs = [p for p in os.listdir(dest_dir) if _is_supported_image_name(p)]
        if existing_imgs:
            LOGGER.info(f'Using existing PDF import folder: {dest_dir}')
            return dest_dir
        if os.listdir(dest_dir):
            raise ArchiveImportError(
                f'Cannot import PDFs into non-empty folder without images: {dest_dir}'
            )
    else:
        os.makedirs(dest_dir)
    return dest_dir


def import_pdfs_to_project(pdf_paths: List[str]) -> str:
    if not pdf_paths:
        raise ArchiveImportError('No PDF files selected.')
    pdf_paths = natsorted(osp.abspath(path) for path in pdf_paths)
    for pdf_path in pdf_paths:
        if not osp.isfile(pdf_path):
            raise ArchiveImportError(f'PDF file does not exist: {pdf_path}')
        if Path(pdf_path).suffix.lower() != '.pdf':
            raise ArchiveImportError(f'Unsupported PDF import selection: {pdf_path}')

    if len(pdf_paths) == 1:
        return import_archive_to_project(pdf_paths[0])

    dest_dir = _prepare_multi_pdf_destination(pdf_paths)
    if [p for p in os.listdir(dest_dir) if _is_supported_image_name(p)]:
        return dest_dir

    LOGGER.info(f'Importing {len(pdf_paths)} PDFs into {dest_dir}')
    used_names = set()
    image_names = []
    image_groups = []
    for pdf_path in natsorted(pdf_paths):
        group_images = _render_pdf_pages(pdf_path, dest_dir, used_names, len(image_names) + 1)
        image_names.extend(group_images)
        image_groups.append({
            'name': _group_name(pdf_path),
            'type': 'pdf',
            'source': osp.abspath(pdf_path),
            'images': group_images,
        })

    if not image_names:
        raise ArchiveImportError('Selected PDFs contain no renderable pages.')

    _write_multi_pdf_metadata(dest_dir, pdf_paths, image_names, image_groups)
    return dest_dir


def _iter_importable_files(root: str, include_images: bool = True) -> Iterable[str]:
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [
            dirname for dirname in dirs
            if dirname not in IMPORT_EXCLUDE_DIRS and not dirname.startswith('.')
        ]
        for filename in files:
            path = osp.join(current_root, filename)
            ext = Path(filename).suffix.lower()
            if ext in ARCHIVE_EXT or (include_images and ext in IMG_EXT):
                yield path


def collect_importable_sources(paths: Sequence[str], include_images: bool = True) -> List[str]:
    sources = []
    for path in paths:
        if osp.isdir(path):
            sources.extend(_iter_importable_files(path, include_images=include_images))
        elif osp.isfile(path) and (Path(path).suffix.lower() in ARCHIVE_EXT or (include_images and Path(path).suffix.lower() in IMG_EXT)):
            sources.append(path)
    return natsorted(
        {osp.abspath(path) for path in sources},
        key=lambda path: (len(Path(path).parts), path),
    )


def has_importable_sources(path: str, include_images: bool = True) -> bool:
    if osp.isfile(path):
        return is_importable_file_path(path) if include_images else is_archive_path(path)
    if not osp.isdir(path):
        return False
    return any(True for _ in _iter_importable_files(path, include_images=include_images))


def import_sources_to_project(source_paths: Sequence[str], include_images: bool = True) -> str:
    if not source_paths:
        raise ArchiveImportError('No import sources selected.')
    source_paths = [osp.abspath(path) for path in source_paths]

    if len(source_paths) == 1 and osp.isfile(source_paths[0]) and is_archive_path(source_paths[0]):
        return import_archive_to_project(source_paths[0])

    importable_sources = collect_importable_sources(source_paths, include_images=include_images)
    if not importable_sources:
        raise ArchiveImportError('No supported images, comic archives, or PDFs found for import.')

    dest_dir = source_collection_project_dir(source_paths)
    if osp.isdir(dest_dir):
        existing_imgs = [p for p in os.listdir(dest_dir) if _is_supported_image_name(p)]
        if existing_imgs:
            LOGGER.info(f'Using existing source collection import folder: {dest_dir}')
            return dest_dir
        if os.listdir(dest_dir):
            raise ArchiveImportError(
                f'Cannot import sources into non-empty folder without images: {dest_dir}'
            )
    else:
        os.makedirs(dest_dir)

    LOGGER.info(f'Importing {len(importable_sources)} sources into {dest_dir}')
    used_names = set()
    image_names = []
    image_groups = []
    group_index = {}
    for source_path in importable_sources:
        ext = Path(source_path).suffix.lower()
        start_index = len(image_names) + 1
        group_name = _group_name(source_path)
        group_type = _source_type(source_path)
        group_source = osp.abspath(source_path)
        if ext in {'.zip', '.cbz'}:
            group_images = _import_zip_archive(source_path, dest_dir, used_names, start_index)
        elif ext == '.cbr':
            group_images = _import_cbr_archive(source_path, dest_dir, used_names, start_index)
        elif ext == '.pdf':
            group_images = _render_pdf_pages(source_path, dest_dir, used_names, start_index)
        elif ext in IMG_EXT:
            group_name = _image_group_for_collection(source_path, source_paths)
            group_type = 'folder'
            group_source = osp.dirname(osp.abspath(source_path))
            group_images = [
                _copy_image_file(
                    source_path,
                    dest_dir,
                    used_names,
                    start_index,
                    source_name=_source_name_for_collection(source_path, source_paths),
                )
            ]
        else:
            group_images = []
        if not group_images:
            continue
        image_names.extend(group_images)
        group_key = (group_name, group_type, group_source)
        if group_key not in group_index:
            group_index[group_key] = len(image_groups)
            image_groups.append({
                'name': group_name,
                'type': group_type,
                'source': group_source,
                'images': [],
            })
        image_groups[group_index[group_key]]['images'].extend(group_images)

    if not image_names:
        raise ArchiveImportError('Selected sources contain no supported image pages.')

    _write_collection_metadata(dest_dir, source_paths, image_names, image_groups)
    return dest_dir


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
    elif ext == '.pdf':
        image_names = _import_pdf(archive_path, dest_dir)
    else:
        image_names = []

    if not image_names:
        raise ArchiveImportError(f'Archive contains no supported image files: {archive_path}')

    _write_metadata(dest_dir, archive_path, image_names)
    return dest_dir
