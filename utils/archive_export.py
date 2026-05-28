import os
import os.path as osp
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import List, Sequence, Tuple

from PIL import Image

from .config import pcfg
from .io_utils import IMG_EXT, find_all_imgs, imread, imwrite
from .logger import logger as LOGGER


EXPORT_EXT = {'.zip', '.cbz', '.cbr', '.pdf'}


class ArchiveExportError(Exception):
    pass


def archive_export_filter() -> str:
    return 'Comic exports (*.cbz *.cbr *.zip *.pdf)'


def is_export_path(path: str) -> bool:
    return Path(path).suffix.lower() in EXPORT_EXT


def default_export_path(project_dir: str, ext: str = '.cbz') -> str:
    ext = ext.lower()
    if not ext.startswith('.'):
        ext = '.' + ext
    if ext not in EXPORT_EXT:
        raise ArchiveExportError(f'Unsupported export extension: {ext}')
    return osp.join(project_dir, osp.basename(osp.normpath(project_dir)) + ext)


def _safe_archive_name(index: int, source_name: str, used_names: set) -> str:
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


def _find_result_image_for_page(project, page_name: str) -> str:
    preferred = project.get_result_path(page_name)
    if osp.exists(preferred):
        return preferred

    result_dir = project.result_dir()
    if not osp.isdir(result_dir):
        return ''

    page_stem = Path(page_name).stem
    candidates = []
    for filename in find_all_imgs(result_dir, abs_path=False, sort=True):
        if Path(filename).stem == page_stem:
            candidates.append(osp.join(result_dir, filename))
    if not candidates:
        return ''
    candidates.sort(key=lambda path: osp.getmtime(path), reverse=True)
    return candidates[0]


def _materialize_ignored_result_images(project) -> List[str]:
    ignored_pages = getattr(project, 'ignored_pages', set()) or set()
    created = []
    for page_name in project.pages.keys():
        if page_name not in ignored_pages:
            continue
        if _find_result_image_for_page(project, page_name):
            continue

        source_path = osp.join(project.directory, page_name)
        if not osp.isfile(source_path):
            raise ArchiveExportError(f'Missing source image for ignored page: {page_name}')

        img = imread(source_path)
        if img is None:
            raise ArchiveExportError(f'Could not read ignored page source image: {page_name}')

        target_path = project.get_result_path(page_name)
        imwrite(target_path, img, ext=pcfg.imgsave_ext, quality=pcfg.imgsave_quality)
        created.append(page_name)
    if created:
        LOGGER.info(f'Copied {len(created)} ignored page(s) to result output for export.')
    return created


def result_images_for_project(project) -> List[Tuple[str, str]]:
    if project is None or getattr(project, 'directory', None) is None:
        raise ArchiveExportError('No project is open.')
    if getattr(project, 'is_empty', False):
        raise ArchiveExportError('The current project has no pages to export.')

    _materialize_ignored_result_images(project)

    missing = []
    images = []
    for page_name in project.pages.keys():
        image_path = _find_result_image_for_page(project, page_name)
        if not image_path:
            missing.append(page_name)
        else:
            images.append((page_name, image_path))

    if missing:
        preview = ', '.join(missing[:5])
        if len(missing) > 5:
            preview += f', ... ({len(missing)} total)'
        raise ArchiveExportError(
            'Missing rendered result images for export. '
            f'Save or run the project first. Missing pages: {preview}'
        )
    return images


def _validate_images(image_paths: Sequence[Tuple[str, str]]) -> None:
    if not image_paths:
        raise ArchiveExportError('No rendered images are available for export.')
    for _, image_path in image_paths:
        if not osp.isfile(image_path):
            raise ArchiveExportError(f'Rendered image does not exist: {image_path}')
        if Path(image_path).suffix.lower() not in IMG_EXT:
            raise ArchiveExportError(f'Unsupported rendered image extension: {image_path}')


def _ensure_parent_dir(path: str) -> None:
    parent = osp.dirname(path)
    if parent and not osp.exists(parent):
        os.makedirs(parent)


def _zip_comic(image_paths: Sequence[Tuple[str, str]], output_path: str) -> str:
    _ensure_parent_dir(output_path)
    used_names = set()
    with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for index, (page_name, image_path) in enumerate(image_paths, start=1):
            arcname = _safe_archive_name(index, page_name, used_names)
            arc_ext = Path(image_path).suffix.lower()
            if Path(arcname).suffix.lower() != arc_ext:
                arcname = str(Path(arcname).with_suffix(arc_ext))
            archive.write(image_path, arcname)
    return output_path


def _flatten_for_pdf(image_path: str) -> Image.Image:
    img = Image.open(image_path)
    img.load()
    if img.mode == 'RGB':
        return img
    if img.mode in {'RGBA', 'LA'} or (img.mode == 'P' and 'transparency' in img.info):
        rgba = img.convert('RGBA')
        background = Image.new('RGB', rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel('A'))
        img.close()
        return background
    converted = img.convert('RGB')
    img.close()
    return converted


def _pdf_comic(image_paths: Sequence[Tuple[str, str]], output_path: str) -> str:
    _ensure_parent_dir(output_path)
    images = [_flatten_for_pdf(image_path) for _, image_path in image_paths]
    try:
        first, rest = images[0], images[1:]
        first.save(output_path, 'PDF', save_all=True, append_images=rest, resolution=72.0)
    finally:
        for image in images:
            image.close()
    return output_path


def _rar_command() -> str:
    for candidate in ('rar', 'WinRAR'):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    if os.name == 'nt':
        for candidate in (
            r'C:\Program Files\WinRAR\Rar.exe',
            r'C:\Program Files (x86)\WinRAR\Rar.exe',
        ):
            if osp.exists(candidate):
                return candidate

    raise ArchiveExportError(
        'CBR export requires a RAR-capable command line tool such as rar or WinRAR. '
        '7z can read CBR/RAR files but usually cannot create them. '
        'Use CBZ, ZIP, or PDF export if rar is not installed.'
    )


def _copy_images_to_temp(image_paths: Sequence[Tuple[str, str]], temp_dir: str) -> List[str]:
    used_names = set()
    copied = []
    for index, (page_name, image_path) in enumerate(image_paths, start=1):
        name = _safe_archive_name(index, page_name, used_names)
        ext = Path(image_path).suffix.lower()
        if Path(name).suffix.lower() != ext:
            name = str(Path(name).with_suffix(ext))
        target = osp.join(temp_dir, name)
        shutil.copy2(image_path, target)
        copied.append(target)
    return copied


def _cbr_comic(image_paths: Sequence[Tuple[str, str]], output_path: str) -> str:
    rar = _rar_command()
    _ensure_parent_dir(output_path)
    if osp.exists(output_path):
        os.remove(output_path)

    with tempfile.TemporaryDirectory(prefix='btrans_cbr_export_') as tmpdir:
        copied = _copy_images_to_temp(image_paths, tmpdir)
        result = subprocess.run(
            [rar, 'a', '-ep1', '-idq', output_path] + [osp.basename(path) for path in copied],
            capture_output=True,
            text=True,
            shell=False,
            cwd=tmpdir,
        )
        if result.returncode != 0 or not osp.exists(output_path):
            raise ArchiveExportError(
                'Failed to create CBR archive with rar.\n'
                f'stdout:\n{result.stdout}\n'
                f'stderr:\n{result.stderr}'
            )
    return output_path


def export_images(image_paths: Sequence[Tuple[str, str]], output_path: str) -> str:
    ext = Path(output_path).suffix.lower()
    if ext not in EXPORT_EXT:
        raise ArchiveExportError(f'Unsupported export extension: {ext}')
    _validate_images(image_paths)

    LOGGER.info(f'Exporting {len(image_paths)} rendered pages to {output_path}')
    if ext in {'.zip', '.cbz'}:
        return _zip_comic(image_paths, output_path)
    if ext == '.pdf':
        return _pdf_comic(image_paths, output_path)
    if ext == '.cbr':
        return _cbr_comic(image_paths, output_path)
    raise ArchiveExportError(f'Unsupported export extension: {ext}')


def export_project(project, output_path: str) -> str:
    return export_images(result_images_for_project(project), output_path)
