from typing import Union, List, Dict, Tuple
import os.path as osp
import os

from . import INPAINTERS, TEXTDETECTORS, OCR, TRANSLATORS
from .base import BaseModule, LOGGER
import utils.shared as shared
from utils.download_util import download_and_check_files, check_local_file


REGISTRY_LABELS = [
    ('inpainter', INPAINTERS),
    ('textdetector', TEXTDETECTORS),
    ('ocr', OCR),
    ('translator', TRANSLATORS),
]

OPTIONAL_STARTUP_DOWNLOADS = {
    ('inpainter', 'aot'),
    ('inpainter', 'flux2-klein'),
    ('ocr', 'PaddleOCRVLManga'),
    ('ocr', 'one_ocr'),
    ('ocr', 'paddle_ocr'),
    ('ocr', 'stariver_ocr'),
}

RUNTIME_MODEL_NOTES = {
    ('ocr', 'paddle_ocr'): 'managed by PaddleOCR on first use',
    ('ocr', 'one_ocr'): 'manual oneocr.dll and oneocr.onemodel files required',
    ('ocr', 'stariver_ocr'): 'API-based OCR, no local model download',
}


def iter_downloadable_modules():
    for category, registry in REGISTRY_LABELS:
        for module_key, module_class in registry.module_dict.items():
            if module_class.download_file_list is None:
                continue
            yield category, module_key, module_class


def _wrap_download_entries(download_kwargs: Dict) -> Tuple[List[str], List[str], List[str]]:
    files = download_kwargs.get('files')
    if not isinstance(files, list):
        files = [files]

    save_files = download_kwargs.get('save_files')
    if save_files is None:
        save_files = files
    elif not isinstance(save_files, list):
        save_files = [save_files]

    sha256_pre_calculated = download_kwargs.get('sha256_pre_calculated')
    if not isinstance(sha256_pre_calculated, list):
        if sha256_pre_calculated is None:
            sha256_pre_calculated = [None] * len(files)
        else:
            sha256_pre_calculated = [sha256_pre_calculated]

    save_dir = download_kwargs.get('save_dir')
    if save_dir is not None:
        save_files = [osp.join(save_dir, savep) for savep in save_files]

    return files, save_files, sha256_pre_calculated


def module_download_status(module_class: BaseModule, verify_hash: bool = False) -> Tuple[bool, List[str]]:
    missing = []
    for download_kwargs in module_class.download_file_list or []:
        _, save_files, sha256_pre_calculated = _wrap_download_entries(download_kwargs)
        for savep, sha256_precal in zip(save_files, sha256_pre_calculated):
            hash_value = sha256_precal if verify_hash else None
            file_exists, valid_hash, _ = check_local_file(savep, hash_value, cache_hash=False)
            if not file_exists or not valid_hash:
                missing.append(savep)
    return not missing, missing


def get_downloadable_model_entries():
    entries = []
    seen = set()
    for category, module_key, module_class in iter_downloadable_modules():
        seen.add((category, module_key))
        ready, missing = module_download_status(module_class)
        entries.append({
            'category': category,
            'key': module_key,
            'module_class': module_class,
            'ready': ready,
            'missing': missing,
            'optional_startup': (category, module_key) in OPTIONAL_STARTUP_DOWNLOADS,
            'downloadable': True,
            'note': '',
        })
    for category, registry in REGISTRY_LABELS:
        for module_key, module_class in registry.module_dict.items():
            marker = (category, module_key)
            if marker in seen or marker not in RUNTIME_MODEL_NOTES:
                continue
            entries.append({
                'category': category,
                'key': module_key,
                'module_class': module_class,
                'ready': True,
                'missing': [],
                'optional_startup': marker in OPTIONAL_STARTUP_DOWNLOADS,
                'downloadable': False,
                'note': RUNTIME_MODEL_NOTES[marker],
            })
    return entries


def download_module_files(module_class: BaseModule) -> bool:
    all_successful = True
    for download_kwargs in module_class.download_file_list or []:
        all_successful = download_and_check_files(**download_kwargs) and all_successful
    return all_successful


def download_and_check_module_files(module_class_list: List[BaseModule] = None):
    if module_class_list is None:
        module_class_list = []
        for category, module_key, module_class in iter_downloadable_modules():
            if (category, module_key) in OPTIONAL_STARTUP_DOWNLOADS:
                LOGGER.info(f'Skipping optional startup model download for {category}/{module_key}. Use Tools -> Model Downloads to fetch it.')
                continue
            module_class_list.append(module_class)

    for module_class in module_class_list:
        if module_class.download_file_on_load or module_class.download_file_list is None:
            continue
        all_successful = download_module_files(module_class)
        if all_successful:
            continue
        LOGGER.error(f'Please save these files manually to sepcified path and restart the application, otherwise {module_class} will be unavailable.')

def prepare_pkuseg():
    try:
        import pkuseg
    except:
        import spacy_pkuseg as pkuseg

    flist = [
        {
            'url': 'https://github.com/lancopku/pkuseg-python/releases/download/v0.0.16/postag.zip',
            'files': ['features.pkl', 'weights.npz'],
            'sha256_pre_calculated': ['17d734c186a0f6e76d15f4990e766a00eed5f72bea099575df23677435ee749d', '2bbd53b366be82a1becedb4d29f76296b36ad7560b6a8c85d54054900336d59a'],
            'archived_files': 'postag.zip',
            'save_dir': 'data/models/pkuseg/postag'
        },
        {
            'url': 'https://github.com/explosion/spacy-pkuseg/releases/download/v0.0.26/spacy_ontonotes.zip',
            'files': ['features.msgpack', 'weights.npz'],
            'sha256_pre_calculated': ['fd4322482a7018b9bce9216173ae9d2848efe6d310b468bbb4383fb55c874a18', '5ada075eb25a854f71d6e6fa4e7d55e7be0ae049255b1f8f19d05c13b1b68c9e'],
            'archived_files': 'spacy_ontonotes.zip',
            'save_dir': 'data/models/pkuseg/spacy_ontonotes'
        },
    ]
    for files_download_kwargs in flist:
        download_and_check_files(**files_download_kwargs)

    PKUSEG_HOME = osp.join(shared.PROGRAM_PATH, 'data/models/pkuseg')
    pkuseg.config.pkuseg_home = PKUSEG_HOME

    # there must be data/models/pkuseg/postag.zip and data/models/pkuseg/spacy_ontonotes.zip
    # otherwise the dumb package download these models again becuz its dumb checking
    p = osp.join(PKUSEG_HOME, 'postag.zip')
    if not osp.exists(p):
        os.makedirs(p)

    p = osp.join(PKUSEG_HOME, 'spacy_ontonotes.zip')
    if not osp.exists(p):
        os.makedirs(p)


def prepare_local_files_forall():

    # download files required by detect, ocr, inpaint and translators
    download_and_check_module_files()

    prepare_pkuseg()

    if shared.CACHE_UPDATED:
        shared.dump_cache()


