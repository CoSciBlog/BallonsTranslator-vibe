import time
from typing import Union, List, Dict, Callable
import os.path as osp

import cv2
import numpy as np
from qtpy.QtCore import QThread, Signal, QObject, QLocale, QTimer
from qtpy.QtWidgets import QFileDialog
from sympy import true

from .funcmaps import get_maskseg_method
from utils.logger import logger as LOGGER
from utils.registry import Registry
from utils.imgproc_utils import enlarge_window, get_block_mask
from utils.io_utils import imread, text_is_empty
from utils.textblock_mask import canny_flood, connected_canny_flood, existing_mask
from utils.decensor import build_decensor_mask, select_decensor_input_image, write_decensor_debug_outputs
from modules.translators import MissingTranslatorParams
from modules.base import BaseModule, soft_empty_cache
from modules import INPAINTERS, TRANSLATORS, TEXTDETECTORS, OCR, \
    GET_VALID_TRANSLATORS, GET_VALID_TEXTDETECTORS, GET_VALID_INPAINTERS, GET_VALID_OCR, \
    BaseTranslator, InpainterBase, TextDetectorBase, OCRBase, merge_config_module_params
import modules
modules.translators.SYSTEM_LANG = QLocale.system().name()
from utils.textblock import TextBlock, sort_regions
from utils import shared
from utils.message import create_error_dialog, create_info_dialog
from .custom_widget import ImgtransProgressMessageBox, ParamComboBox
from .configpanel import ConfigPanel
from utils.proj_imgtrans import ProjImgTrans
from utils.config import pcfg, RunStatus
cfg_module = pcfg.module


def _mask_has_pixels(mask: np.ndarray) -> bool:
    return mask is not None and np.any(mask > 0)


def _post_process_blktrans_mask(mask: np.ndarray, post_process_mask: Callable = None) -> np.ndarray:
    if mask is None:
        return None
    if post_process_mask is not None:
        return post_process_mask(mask)
    ksize = pcfg.drawpanel.recttool_dilate_ksize
    if ksize == 0:
        return mask
    element = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * ksize + 1, 2 * ksize + 1), (ksize, ksize))
    return cv2.dilate(mask, element)


def _textbox_inpaint_mask(img: np.ndarray, mask: np.ndarray, post_process_mask: Callable = None) -> np.ndarray:
    preferred_method = get_maskseg_method()
    methods = [preferred_method, canny_flood, connected_canny_flood]
    if _mask_has_pixels(mask):
        methods.insert(0, existing_mask)

    seen = set()
    for method in methods:
        if method in seen:
            continue
        seen.add(method)
        try:
            inpaint_mask_array, _ballon_mask, _bub_dict = method(img, mask=mask)
        except Exception as e:
            LOGGER.debug(f'Textbox inpaint mask method {getattr(method, "__name__", method)} failed: {e}')
            continue

        processed_mask = _post_process_blktrans_mask(inpaint_mask_array, post_process_mask)
        if _mask_has_pixels(processed_mask):
            return processed_mask
    return None


class ModuleThread(QThread):

    finish_set_module = Signal()
    _failed_set_module_msg = 'Failed to set module.'
    module_thread_stopped = Signal()

    def __init__(self, module_key: str, MODULE_REGISTER: Registry, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.job = None
        self.module: Union[TextDetectorBase, BaseTranslator, InpainterBase, OCRBase] = None
        self.module_register = MODULE_REGISTER
        self.module_key = module_key

        self.pipeline_pagekey_queue = []
        self.finished_counter = 0
        self.num_process_pages = 0
        self.imgtrans_proj: ProjImgTrans = None
        self.stop_requested = False

    def _set_module(self, module_name: str):
        old_module = self.module
        try:
            module: Union[TextDetectorBase, BaseTranslator, InpainterBase, OCRBase] \
                = self.module_register.module_dict[module_name]
            params = cfg_module.get_params(self.module_key)[module_name]
            if params is not None:
                self.module = module(**params)
            else:
                self.module = module()
            if not pcfg.module.load_model_on_demand:
                self.module.load_model()
            if old_module is not None:
                del old_module
        except Exception as e:
            self.module = old_module
            create_error_dialog(e, self._failed_set_module_msg)

        self.finish_set_module.emit()

    def pipeline_finished(self):
        if self.imgtrans_proj is None:
            return True
        elif self.finished_counter >= self.num_process_pages:
            return True
        return False

    def initImgtransPipeline(self, proj: ProjImgTrans):
        if self.isRunning():
            self.terminate()
        self.imgtrans_proj = proj
        self.finished_counter = 0
        self.pipeline_pagekey_queue.clear()

    def requestStop(self):
        self.stop_requested = True

    def run(self):
        if self.job is not None:
            self.job()
        self.job = None


class InpaintThread(ModuleThread):

    finish_inpaint = Signal(dict)
    inpainting = False    
    inpaint_failed = Signal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__('inpainter', INPAINTERS, *args, **kwargs)

    @property
    def inpainter(self) -> InpainterBase:
        return self.module

    def setInpainter(self, inpainter: str):
        self.job = lambda : self._set_module(inpainter)
        self.start()

    def inpaint(self, img: np.ndarray, mask: np.ndarray, img_key: str = None, inpaint_rect=None, **metadata):
        self.job = lambda : self._inpaint(img, mask, img_key, inpaint_rect, **metadata)
        self.start()
    
    def _inpaint(self, img: np.ndarray, mask: np.ndarray, img_key: str = None, inpaint_rect=None, **metadata):
        inpaint_dict = {}
        self.inpainting = True
        try:
            inpainted = self.inpainter.inpaint(img, mask)
            inpaint_dict = {
                'inpainted': inpainted,
                'img': img,
                'mask': mask,
                'img_key': img_key,
                'inpaint_rect': inpaint_rect
            }
            inpaint_dict.update(metadata)
            self.finish_inpaint.emit(inpaint_dict)
        except Exception as e:
            create_error_dialog(e, self.tr('Inpainting Failed.'), 'InpaintFailed')
            self.inpainting = False
            self.inpaint_failed.emit()
        self.inpainting = False


class TextDetectThread(ModuleThread):
    
    finish_detect_page = Signal(str)
    def __init__(self, *args, **kwargs) -> None:
        super().__init__('textdetector', TEXTDETECTORS, *args, **kwargs)

    def setTextDetector(self, textdetector: str):
        self.job = lambda : self._set_module(textdetector)
        self.start()

    @property
    def textdetector(self) -> TextDetectorBase:
        return self.module


class OCRThread(ModuleThread):

    finish_ocr_page = Signal(str)
    def __init__(self, *args, **kwargs) -> None:
        super().__init__('ocr', OCR, *args, **kwargs)

    def setOCR(self, ocr: str):
        self.job = lambda : self._set_module(ocr)
        self.start()
    
    @property
    def ocr(self) -> OCRBase:
        return self.module


class TranslateThread(ModuleThread):

    finish_translate_page = Signal(str)
    progress_changed = Signal(int)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__('translator', TRANSLATORS, *args, **kwargs)
        self.translator: BaseTranslator = self.module

    def _set_translator(self, translator: str):
        
        old_translator = self.translator
        source, target = cfg_module.translate_source, cfg_module.translate_target
        if self.translator is not None:
            if self.translator.name == translator:
                return
        
        try:
            params = cfg_module.translator_params[translator]
            translator_module: BaseTranslator = TRANSLATORS.module_dict[translator]
            if params is not None:
                self.translator = translator_module(source, target, raise_unsupported_lang=False, **params)
            else:
                self.translator = translator_module(source, target, raise_unsupported_lang=False)
            cfg_module.translate_source = self.translator.lang_source
            cfg_module.translate_target = self.translator.lang_target
            cfg_module.translator = self.translator.name
        except Exception as e:
            if old_translator is None:
                old_translator = TRANSLATORS.module_dict['google']('简体中文', 'English', raise_unsupported_lang=False)
            self.translator = old_translator
            msg = self.tr('Failed to set translator ') + translator
            create_error_dialog(e, msg, 'FailedSetTranslator')

        self.module = self.translator
        self.finish_set_module.emit()

    def setTranslator(self, translator: str):
        if translator in ['Sugoi']:
            self._set_translator(translator)
        else:
            self.job = lambda : self._set_translator(translator)
            self.start()

    def _set_translator_page_context(self, page_key: str):
        if self.translator is not None and hasattr(self.translator, 'set_page_context'):
            self.translator.set_page_context(self.imgtrans_proj, page_key)

    def _clear_translator_page_context(self):
        if self.translator is not None and hasattr(self.translator, 'clear_page_context'):
            self.translator.clear_page_context()

    def _translate_page(self, page_dict, page_key: str, emit_finished=True):
        page = page_dict[page_key]
        try:
            self._set_translator_page_context(page_key)
            self.translator.translate_textblk_lst(page)
            if (
                pcfg.module.pronoun_review_after_translation
                and hasattr(self.translator, 'supports_translation_review')
                and self.translator.supports_translation_review()
            ):
                LOGGER.info(f'Running post-translation pronoun/address review for {page_key}.')
                self.translator.review_textblk_lst(page)
        except Exception as e:
            create_error_dialog(e, self.tr('Translation Failed.'), 'TranslationFailed')
        finally:
            self._clear_translator_page_context()
        if emit_finished:
            self.finish_translate_page.emit(page_key)

    def translatePage(self, page_dict, page_key: str, imgtrans_proj: ProjImgTrans = None):
        if imgtrans_proj is not None:
            self.imgtrans_proj = imgtrans_proj
        self.job = lambda: self._translate_page(page_dict, page_key)
        self.start()

    def push_pagekey_queue(self, page_key: str):
        self.pipeline_pagekey_queue.append(page_key)

    def runTranslatePipeline(self, imgtrans_proj: ProjImgTrans):
        self.initImgtransPipeline(imgtrans_proj)
        self.job = self._run_translate_pipeline
        self.start()

    def runPretranslatePipeline(self, imgtrans_proj: ProjImgTrans):
        self.initImgtransPipeline(imgtrans_proj)
        self.job = self._run_pretranslate_pipeline
        self.start()

    def _run_pretranslate_pipeline(self):
        if not hasattr(self.translator, 'pretranslate_textblk_lst'):
            return

        while not self.pipeline_finished():
            if self.stop_requested:
                self.module_thread_stopped.emit()
                self.stop_requested = False
                break

            if len(self.pipeline_pagekey_queue) == 0:
                time.sleep(0.1)
                continue

            page_key = self.pipeline_pagekey_queue.pop(0)
            try:
                self.translator.pretranslate_textblk_lst(self.imgtrans_proj.pages[page_key])
            except Exception as e:
                LOGGER.warning(f'Background first-step translation failed for {page_key}: {e}')
            self.finished_counter += 1


    def _run_translate_pipeline(self):
        delay = self.translator.delay()

        while not self.pipeline_finished():
            if self.stop_requested:
                self.module_thread_stopped.emit()
                self.stop_requested = False
                break

            if len(self.pipeline_pagekey_queue) == 0:
                time.sleep(0.1)
                continue
            
            page_key = self.pipeline_pagekey_queue.pop(0)
            self.blockSignals(True)
            trans_success = True
            try:
                self._translate_page(self.imgtrans_proj.pages, page_key, emit_finished=False)
            except Exception as e:
                # TODO: allowing retry/skip/terminate
                trans_success = False
                msg = self.tr('Translation Failed.')
                if isinstance(e, MissingTranslatorParams):
                    msg = msg + '\n' + str(e) + self.tr(' is required for ' + self.translator.name)
                    
                self.blockSignals(False)
                create_error_dialog(e, msg, 'TranslationFailed')
                # self.imgtrans_proj = None
                # self.finished_counter = 0
                # self.pipeline_pagekey_queue = []
                # return
            self.blockSignals(False)
            self.finished_counter += 1
            if trans_success:
                self.imgtrans_proj.update_page_progress(page_key, RunStatus.FIN_TRANSLATE)
            self.progress_changed.emit(self.finished_counter)

            if not self.pipeline_finished() and delay > 0:
                time.sleep(delay)


class ImgtransThread(QThread):

    pipeline_stopped = Signal()
    update_detect_progress = Signal(int)
    update_ocr_progress = Signal(int)
    update_translate_progress = Signal(int)
    update_inpaint_progress = Signal(int)
    update_decensor_progress = Signal(int)

    finish_blktrans_stage = Signal(str, int)
    finish_blktrans = Signal(int, list)
    unload_modules = Signal(list)

    detect_counter = 0
    ocr_counter = 0
    translate_counter = 0
    inpaint_counter = 0
    decensor_counter = 0

    def __init__(self, 
                 textdetect_thread: TextDetectThread,
                 ocr_thread: OCRThread,
                 translate_thread: TranslateThread,
                 inpaint_thread: InpaintThread,
                 *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.textdetect_thread = textdetect_thread
        self.ocr_thread = ocr_thread
        self.translate_thread = translate_thread
        self.translate_thread.module_thread_stopped.connect(self.on_module_thread_stopped)
        self.inpaint_thread = inpaint_thread
        self.job = None
        self.imgtrans_proj: ProjImgTrans = None
        self.stop_requested = False
        self.pages_to_process = None  # 需要处理的页面列表（用于继续运行模式）
        self.ocr_fallback_name = ''
        self.ocr_fallback = None

        self.translation_only = False
        self.review_only = False
        self.decensor_only = False
        self.inpaint_optimization_only = False
        self.blktrans_page_key = None

    def on_module_thread_stopped(self):
        while True:
            # might freeze UI
            if self.translate_thread.isRunning() or self.inpaint_thread.isRunning() or self.ocr_thread.isRunning() or self.textdetect_thread.isRunning():
                time.sleep(0.05)
                continue
            break

        self.pipeline_stopped.emit()

    @property
    def textdetector(self) -> TextDetectorBase:
        return self.textdetect_thread.textdetector

    @property
    def ocr(self) -> OCRBase:
        return self.ocr_thread.ocr
    
    @property
    def translator(self) -> BaseTranslator:
        return self.translate_thread.translator

    @property
    def inpainter(self) -> InpainterBase:
        return self.inpaint_thread.inpainter

    def _set_translator_page_context(self, page_key: str):
        if self.translator is not None and hasattr(self.translator, 'set_page_context'):
            self.translator.set_page_context(self.imgtrans_proj, page_key)

    def _clear_translator_page_context(self):
        if self.translator is not None and hasattr(self.translator, 'clear_page_context'):
            self.translator.clear_page_context()

    def configure_ocr_fallback(self, module_name: str = ''):
        self.ocr_fallback_name = module_name or ''
        self.ocr_fallback = None

    def _run_ocr_with_fallback(self, img: np.ndarray, blk_list: List[TextBlock]):
        self.ocr.run_ocr(img, blk_list)
        if (
            not self.ocr_fallback_name
            or self.ocr_fallback_name == getattr(self.ocr, 'name', '')
            or not blk_list
            or any(not text_is_empty(blk.get_text()) for blk in blk_list)
        ):
            return
        if self.ocr_fallback is None:
            fallback_class = OCR.module_dict[self.ocr_fallback_name]
            params = cfg_module.get_params('ocr').get(self.ocr_fallback_name)
            self.ocr_fallback = fallback_class(**params) if params is not None else fallback_class()
            if not pcfg.module.load_model_on_demand:
                self.ocr_fallback.load_model()
        LOGGER.info(f'OCR returned no text; retrying with fallback {self.ocr_fallback_name}.')
        self.ocr_fallback.run_ocr(img, blk_list)

    def _translate_textblocks(self, imgname: str, blk_list: List[TextBlock]):
        try:
            if imgname:
                self._set_translator_page_context(imgname)
            self.translator.translate_textblk_lst(blk_list)
            if (
                pcfg.module.pronoun_review_after_translation
                and hasattr(self.translator, 'supports_translation_review')
                and self.translator.supports_translation_review()
            ):
                LOGGER.info(f'Running post-translation pronoun/address review for {imgname}.')
                self.translator.review_textblk_lst(blk_list)
        finally:
            self._clear_translator_page_context()

    def _review_textblocks(self, imgname: str, blk_list: List[TextBlock]):
        try:
            if imgname:
                self._set_translator_page_context(imgname)
            self.translator.review_textblk_lst(blk_list)
        finally:
            self._clear_translator_page_context()

    def _shorten_textblocks(self, imgname: str, blk_list: List[TextBlock]):
        try:
            if imgname:
                self._set_translator_page_context(imgname)
            self.translator.rewrite_and_shorten_textblk_lst(blk_list)
        finally:
            self._clear_translator_page_context()

    def _review_address_textblocks(self, imgname: str, blk_list: List[TextBlock]):
        try:
            if imgname:
                self._set_translator_page_context(imgname)
            self.translator.review_address_textblk_lst(blk_list)
        finally:
            self._clear_translator_page_context()

    def _review_uncensored_textblocks(self, imgname: str, blk_list: List[TextBlock]):
        try:
            if imgname:
                self._set_translator_page_context(imgname)
            self.translator.review_uncensored_textblk_lst(blk_list)
        finally:
            self._clear_translator_page_context()

    def runImgtransPipeline(self, imgtrans_proj: ProjImgTrans, pages_to_process=None):
        self.imgtrans_proj = imgtrans_proj
        self.pages_to_process = pages_to_process  # 保存需要处理的页面列表
        self.num_pages = len(self.imgtrans_proj.pages)
        self.stop_requested = False
        self.translation_only = False
        self.review_only = False
        self.decensor_only = False
        self.inpaint_optimization_only = False
        # 创建处理索引到实际页面索引的映射
        self.process_idx_to_page_idx = {}
        self.job = self._imgtrans_pipeline
        self.start()

    def runTranslateOnlyPipeline(self, imgtrans_proj: ProjImgTrans, pages_to_process=None):
        self.imgtrans_proj = imgtrans_proj
        self.pages_to_process = pages_to_process
        self.num_pages = len(self.imgtrans_proj.pages)
        self.stop_requested = False
        self.translation_only = True
        self.review_only = False
        self.decensor_only = False
        self.inpaint_optimization_only = False
        self.process_idx_to_page_idx = {}
        self.job = self._translate_only_pipeline
        self.start()

    def runReviewPipeline(self, imgtrans_proj: ProjImgTrans, pages_to_process=None):
        self.imgtrans_proj = imgtrans_proj
        self.pages_to_process = pages_to_process
        self.num_pages = len(self.imgtrans_proj.pages)
        self.stop_requested = False
        self.translation_only = False
        self.review_only = True
        self.decensor_only = False
        self.inpaint_optimization_only = False
        self.process_idx_to_page_idx = {}
        self.job = self._review_pipeline
        self.start()

    def runDecensorPipeline(self, imgtrans_proj: ProjImgTrans, pages_to_process=None):
        self.imgtrans_proj = imgtrans_proj
        self.pages_to_process = pages_to_process
        self.num_pages = len(self.imgtrans_proj.pages)
        self.stop_requested = False
        self.translation_only = False
        self.review_only = False
        self.decensor_only = True
        self.inpaint_optimization_only = False
        self.process_idx_to_page_idx = {}
        self.job = self._decensor_pipeline
        self.start()

    def runInpaintOptimizationPipeline(self, imgtrans_proj: ProjImgTrans, pages_to_process=None):
        self.imgtrans_proj = imgtrans_proj
        self.pages_to_process = pages_to_process
        self.num_pages = len(self.imgtrans_proj.pages)
        self.stop_requested = False
        self.translation_only = False
        self.review_only = False
        self.decensor_only = False
        self.inpaint_optimization_only = True
        self.process_idx_to_page_idx = {}
        self.job = self._inpaint_optimization_pipeline
        self.start()
    
    def requestStop(self):
        """请求停止当前任务"""
        if self.isRunning():
            self.stop_requested = True
        # 同时停止翻译线程
        if self.translate_thread.isRunning():
            self.translate_thread.requestStop()

    def runBlktransPipeline(self, blk_list: List[TextBlock], tgt_img: np.ndarray, mode: int, blk_ids: List[int], tgt_mask, page_key: str = None):
        self.blktrans_page_key = page_key
        self.job = lambda : self._blktrans_pipeline(blk_list, tgt_img, mode, blk_ids, tgt_mask)
        self.start()

    def _blktrans_pipeline(self, blk_list: List[TextBlock], tgt_img: np.ndarray, mode: int, blk_ids: List[int], tgt_mask):
        if mode == -2:
            self._review_textblocks(self.blktrans_page_key, blk_list)
            self.finish_blktrans.emit(mode, blk_ids)
            return
        if mode == -3:
            self._shorten_textblocks(self.blktrans_page_key, blk_list)
            self.finish_blktrans.emit(mode, blk_ids)
            return
        if mode == -4:
            self._review_address_textblocks(self.blktrans_page_key, blk_list)
            self.finish_blktrans.emit(mode, blk_ids)
            return
        if mode == -5:
            self._review_uncensored_textblocks(self.blktrans_page_key, blk_list)
            self.finish_blktrans.emit(mode, blk_ids)
            return
        if mode >= 0 and mode < 3:
            try:
                self.ocr_thread.module.run_ocr(tgt_img, blk_list, split_textblk=True)
            except Exception as e:
                create_error_dialog(e, self.tr('OCR Failed.'), 'OCRFailed')
            self.finish_blktrans.emit(mode, blk_ids)

        if mode != 0 and mode < 3:
            self._translate_textblocks(self.blktrans_page_key, blk_list)
            self.finish_blktrans.emit(mode, blk_ids)
        if mode > 1:
            im_h, im_w = tgt_img.shape[:2]
            progress_prod = 100. / len(blk_list) if len(blk_list) > 0 else 0
            for ii, blk in enumerate(blk_list):
                xyxy = enlarge_window(blk.xyxy, im_w, im_h)
                xyxy = np.array(xyxy)
                x1, y1, x2, y2 = xyxy.astype(np.int64)
                blk.region_inpaint_dict = None
                if y2 - y1 > 2 and x2 - x1 > 2:
                    im = np.copy(tgt_img[y1: y2, x1: x2])
                    mask_crop = None
                    if tgt_mask is not None:
                        mask_crop = tgt_mask[y1: y2, x1: x2]
                    if mask_crop is None:
                        mask_crop = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
                    mask = _textbox_inpaint_mask(
                        im,
                        mask_crop,
                        getattr(self, 'post_process_mask', None),
                    )
                    if _mask_has_pixels(mask):
                        inpainted = self.inpaint_thread.inpainter.inpaint(im, mask)
                        blk.region_inpaint_dict = {'img': im, 'mask': mask, 'inpaint_rect': [x1, y1, x2, y2], 'inpainted': inpainted}
                    self.finish_blktrans_stage.emit('inpaint', int((ii+1) * progress_prod))
        self.finish_blktrans.emit(mode, blk_ids)

    def _iter_pipeline_pages(self, skip_ignored: bool = True):
        all_pages = list(self.imgtrans_proj.pages.keys())
        pages_to_iterate = self.imgtrans_proj.pipeline_pages(self.pages_to_process, skip_ignored=skip_ignored)
        if self.pages_to_process is not None and len(self.pages_to_process) > 0:
            LOGGER.info(f'Processing specific pages: {len(pages_to_iterate)} pages')
        else:
            LOGGER.info(f'Processing all {len(pages_to_iterate)} pages')

        self.num_pages = max(1, len(pages_to_iterate))
        self.process_idx_to_page_idx = {}
        for process_idx, page_name in enumerate(pages_to_iterate):
            self.process_idx_to_page_idx[process_idx] = all_pages.index(page_name)
        return pages_to_iterate

    def _decensor_page(self, imgname: str):
        img, input_source = select_decensor_input_image(self.imgtrans_proj, imgname)
        LOGGER.info(
            f'Censor Restoration input image source: {input_source} '
            f'for {imgname}, size={img.shape[1]}x{img.shape[0]}'
        )

        censor_mask, mode, debug = build_decensor_mask(
            img,
            mode=pcfg.decensor_mask_mode,
            dilate=pcfg.decensor_mask_dilate,
            min_area_ratio=pcfg.decensor_min_area_ratio,
            return_debug=True,
        )
        debug["input_source"] = input_source
        debug["mask_source"] = "censor_restoration_detector"
        mask_pixel_count = int(np.count_nonzero(censor_mask))
        mask_coverage = mask_pixel_count / max(1, censor_mask.size)
        decensor_box_count = self._count_mask_boxes(censor_mask)
        LOGGER.info(
            f'Censor Restoration detected {decensor_box_count} decensor boxes on {imgname}; '
            f'mask coverage={mask_coverage:.2%}; input_source={input_source}.'
        )
        if pcfg.decensor_save_debug_masks:
            debug_dir = osp.join(
                self.imgtrans_proj.directory,
                'debug',
                'censor_restoration',
                osp.splitext(osp.basename(imgname))[0],
            )
            debug_paths = write_decensor_debug_outputs(debug_dir, img, censor_mask, debug, input_source)
            LOGGER.info(f'Censor Restoration debug overlays saved to {debug_dir}: {debug_paths}')

        self.imgtrans_proj.save_decensor_mask(imgname, censor_mask)

        if np.any(censor_mask > 0):
            decensored = self.inpainter.inpaint(img, censor_mask, self.imgtrans_proj.pages.get(imgname, []))
            LOGGER.info(f'Decensor mask mode "{mode}" applied to {imgname}.')
        else:
            decensored = np.copy(img)
            LOGGER.info(
                f'No decensor mask found for {imgname}. '
                f'The text inpaint mask will not be used automatically. '
                f'debug={debug}. No censor mask found. '
                f'Try debug masks or adjust gray/banded censor detection settings.'
            )

        self.imgtrans_proj.save_decensored(imgname, decensored)
        self.imgtrans_proj.save_inpainted(imgname, decensored)

    def _count_mask_boxes(self, mask: np.ndarray) -> int:
        try:
            import cv2
            contours, _ = cv2.findContours((mask > 0).astype(np.uint8) * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            return len(contours)
        except Exception:
            return 1 if np.any(mask > 0) else 0

    def _run_decensor_pages(self, pages_to_iterate):
        for imgname in pages_to_iterate:
            if self.stop_requested:
                LOGGER.info('Decensor pipeline stopped by user')
                break
            try:
                self._decensor_page(imgname)
            except Exception as e:
                create_error_dialog(e, self.tr('Decensoring Failed.'), 'DecensorFailed')
            self.decensor_counter += 1
            self.update_decensor_progress.emit(self.decensor_counter)

    def _inpaint_optimization_source(self, imgname: str) -> np.ndarray:
        inpainted = self.imgtrans_proj.load_inpainted_by_imgname(imgname)
        if inpainted is not None:
            return inpainted
        return self.imgtrans_proj.ensure_upscaled_img(imgname)

    def _optimize_inpaint_page(self, imgname: str, source_img: np.ndarray = None) -> bool:
        if self.textdetector is None or self.inpainter is None:
            LOGGER.info('Inpaint optimization skipped because detector or inpainter is not loaded.')
            return False

        source_img = source_img if source_img is not None else self._inpaint_optimization_source(imgname)
        if source_img is None:
            return False

        try:
            residual_mask, residual_blocks = self.textdetector.detect(source_img, self.imgtrans_proj)
        except Exception as e:
            create_error_dialog(e, self.tr('Inpaint Optimization Detection Failed.'), 'TextDetectFailed')
            return False

        if residual_mask is None or not np.any(residual_mask > 0):
            LOGGER.info(f'Inpaint optimization found no residual text mask on {imgname}.')
            return False

        residual_pixels = int(np.count_nonzero(residual_mask))
        existing_mask = self.imgtrans_proj.load_mask_by_imgname(imgname)
        if existing_mask is not None and existing_mask.shape[:2] == residual_mask.shape[:2]:
            self.imgtrans_proj.save_mask(imgname, np.bitwise_or(existing_mask, residual_mask))
        else:
            self.imgtrans_proj.save_mask(imgname, residual_mask)

        try:
            optimized = self.inpainter.inpaint(
                source_img,
                residual_mask,
                residual_blocks or self.imgtrans_proj.pages.get(imgname, []),
            )
            self.imgtrans_proj.save_inpainted(imgname, optimized)
            LOGGER.info(
                f'Inpaint optimization repaired {residual_pixels} residual mask pixels on {imgname}.'
            )
            return True
        except Exception as e:
            create_error_dialog(e, self.tr('Inpaint Optimization Failed.'), 'InpaintFailed')
            return False

    def _inpaint_optimization_pipeline(self):
        self.detect_counter = 0
        self.ocr_counter = 0
        self.translate_counter = 0
        self.inpaint_counter = 0
        self.decensor_counter = 0
        pages_to_iterate = self._iter_pipeline_pages(skip_ignored=True)
        self.inpaint_thread.num_process_pages = self.num_pages
        LOGGER.info(f'Running inpaint optimization for {len(pages_to_iterate)} pages')

        for imgname in pages_to_iterate:
            if self.stop_requested:
                LOGGER.info('Inpaint optimization stopped by user')
                break
            self._optimize_inpaint_page(imgname)
            self.inpaint_counter += 1
            self.imgtrans_proj.update_page_progress(imgname, RunStatus.FIN_INPAINT)
            self.update_inpaint_progress.emit(self.inpaint_counter)

        if self.stop_requested:
            self.pipeline_stopped.emit()

    def _imgtrans_pipeline(self):
        self.detect_counter = 0
        self.ocr_counter = 0
        self.translate_counter = 0
        self.inpaint_counter = 0
        self.decensor_counter = 0
        
        # 如果指定了pages_to_process，只处理这些页面
        pages_to_iterate = self._iter_pipeline_pages()
        self.textdetect_thread.num_process_pages = self.num_pages
        self.ocr_thread.num_process_pages = self.num_pages
        self.inpaint_thread.num_process_pages = self.num_pages
        self.translate_thread.num_process_pages = self.num_pages

        low_vram_trans = False
        background_first_step_trans = False
        unload_before_llm_refinement = False
        translate_after_image_processing = bool(
            cfg_module.translate_after_image_processing
        )
        if self.translator is not None:
            low_vram_trans = self.translator.low_vram_mode
            background_first_step_trans = bool(
                not translate_after_image_processing
                and hasattr(self.translator, 'pipeline_pretranslation_enabled')
                and self.translator.pipeline_pretranslation_enabled()
            )
            unload_before_llm_refinement = bool(
                hasattr(self.translator, 'should_unload_before_llm_refinement')
                and self.translator.should_unload_before_llm_refinement()
            )
            self.parallel_trans = not self.translator.is_computational_intensive() \
                and not low_vram_trans \
                and not translate_after_image_processing \
                and not background_first_step_trans \
                and not unload_before_llm_refinement
        else:
            self.parallel_trans = False
        if self.parallel_trans and cfg_module.enable_translate:
            self.translate_thread.runTranslatePipeline(self.imgtrans_proj)
        elif background_first_step_trans and cfg_module.enable_translate:
            self.translate_thread.runPretranslatePipeline(self.imgtrans_proj)

        for imgname in pages_to_iterate:
            
            # 检查是否请求停止
            if self.stop_requested:
                LOGGER.info('Image translation pipeline stopped by user')
                break
                
            img = self.imgtrans_proj.ensure_upscaled_img(imgname)
            mask = blk_list = None
            need_save_mask = False
            blk_removed: List[TextBlock] = []
            if cfg_module.enable_detect:
                try:
                    mask, blk_list = self.textdetector.detect(img, self.imgtrans_proj)
                    need_save_mask = True
                except Exception as e:
                    create_error_dialog(e, self.tr('Text Detection Failed.'), 'TextDetectFailed')
                    blk_list = []
                self.detect_counter += 1
                if pcfg.module.keep_exist_textlines:
                    blk_list = self.imgtrans_proj.pages[imgname] + blk_list
                    blk_list = sort_regions(blk_list)
                    existed_mask = self.imgtrans_proj.load_mask_by_imgname(imgname)
                    if existed_mask is not None:
                        mask = np.bitwise_or(mask, existed_mask)
                self.imgtrans_proj.pages[imgname] = blk_list

                if mask is not None and not cfg_module.enable_ocr:
                    self.imgtrans_proj.save_mask(imgname, mask)
                    need_save_mask = False
                    
                self.imgtrans_proj.update_page_progress(imgname, RunStatus.FIN_DET)
                self.update_detect_progress.emit(self.detect_counter)

            if blk_list is None:
                blk_list = self.imgtrans_proj.pages[imgname] if imgname in self.imgtrans_proj.pages else []

            if cfg_module.enable_ocr:
                try:
                    self._run_ocr_with_fallback(img, blk_list)
                except Exception as e:
                    create_error_dialog(e, self.tr('OCR Failed.'), 'OCRFailed')
                self.ocr_counter += 1

                if pcfg.restore_ocr_empty:
                    blk_list_updated = []
                    for blk in blk_list:
                        text = blk.get_text()
                        if text_is_empty(text):
                            blk_removed.append(blk)
                        else:
                            blk_list_updated.append(blk)

                    if len(blk_removed) > 0:
                        blk_list.clear()
                        blk_list += blk_list_updated
                        
                        if mask is None:
                            mask = self.imgtrans_proj.load_mask_by_imgname(imgname)
                        if mask is not None:
                            inpainted = None
                            if not cfg_module.enable_inpaint:
                                inpainted = self.imgtrans_proj.load_inpainted_by_imgname(imgname)
                            for blk in blk_removed:
                                xywh = blk.bounding_rect()
                                blk_mask, xyxy = get_block_mask(xywh, mask, blk.angle)
                                x1, y1, x2, y2 = xyxy
                                if blk_mask is not None:
                                    mask[y1: y2, x1: x2] = 0
                                    if inpainted is not None:
                                        mskpnt = np.where(blk_mask)
                                        inpainted[y1: y2, x1: x2][mskpnt] = img[y1: y2, x1: x2][mskpnt]
                                    need_save_mask = True
                            if inpainted is not None and need_save_mask:
                                self.imgtrans_proj.save_inpainted(imgname, inpainted)
                            if need_save_mask:
                                self.imgtrans_proj.save_mask(imgname, mask)
                                need_save_mask = False

                self.imgtrans_proj.update_page_progress(imgname, RunStatus.FIN_OCR)
                self.update_ocr_progress.emit(self.ocr_counter)

            if need_save_mask and mask is not None:
                self.imgtrans_proj.save_mask(imgname, mask)
                need_save_mask = False

            if cfg_module.enable_translate:
                if background_first_step_trans:
                    self.translate_thread.push_pagekey_queue(imgname)
                elif self.parallel_trans:
                    self.translate_thread.push_pagekey_queue(imgname)
                elif not low_vram_trans and not translate_after_image_processing:
                    self._translate_textblocks(imgname, blk_list)
                    self.translate_counter += 1
                    self.update_translate_progress.emit(self.translate_counter)
                        
            if cfg_module.enable_inpaint:
                if mask is None:
                    mask = self.imgtrans_proj.load_mask_by_imgname(imgname)
                    
                if mask is not None:
                    try:
                        inpainted = self.inpainter.inpaint(img, mask, blk_list)
                        self.imgtrans_proj.save_inpainted(imgname, inpainted)
                        if cfg_module.enable_inpaint_optimization and not self.stop_requested:
                            self._optimize_inpaint_page(imgname, inpainted)
                    except Exception as e:
                        create_error_dialog(e, self.tr('Inpainting Failed.'), 'InpaintFailed')
                    
                self.inpaint_counter += 1
                self.imgtrans_proj.update_page_progress(imgname, RunStatus.FIN_INPAINT)
                self.update_inpaint_progress.emit(self.inpaint_counter)
            else:
                if len(blk_removed) > 0:
                    self.imgtrans_proj.load_mask_by_imgname
        
        if cfg_module.enable_translate and (
            low_vram_trans
            or background_first_step_trans
            or translate_after_image_processing
            or unload_before_llm_refinement
        ):
            if background_first_step_trans:
                while self.translate_thread.isRunning():
                    if self.stop_requested:
                        self.translate_thread.requestStop()
                        LOGGER.info('Waiting for background first-step translation to stop')
                    time.sleep(0.05)

            if low_vram_trans or unload_before_llm_refinement:
                unload_modules(self, ['textdetector', 'inpainter', 'ocr'])
            for imgname in pages_to_iterate:
                # 检查是否请求停止
                if self.stop_requested:
                    LOGGER.info('Translation stopped by user')
                    break
                    
                blk_list = self.imgtrans_proj.pages[imgname]
                self._translate_textblocks(imgname, blk_list)
                self.translate_counter += 1
                self.imgtrans_proj.update_page_progress(imgname, RunStatus.FIN_TRANSLATE)
                self.update_translate_progress.emit(self.translate_counter)

        if self.stop_requested and (not cfg_module.enable_translate or not self.parallel_trans):
            self.pipeline_stopped.emit()

    def _translate_only_pipeline(self):
        self.detect_counter = 0
        self.ocr_counter = 0
        self.translate_counter = 0
        self.inpaint_counter = 0
        self.decensor_counter = 0

        all_pages = list(self.imgtrans_proj.pages.keys())
        pages_to_iterate = self.imgtrans_proj.pipeline_pages(self.pages_to_process, skip_ignored=True)

        self.num_pages = max(1, len(pages_to_iterate))
        for process_idx, page_name in enumerate(pages_to_iterate):
            self.process_idx_to_page_idx[process_idx] = all_pages.index(page_name)

        self.translate_thread.num_process_pages = self.num_pages
        LOGGER.info(f'Running translation only for {len(pages_to_iterate)} pages')

        for imgname in pages_to_iterate:
            if self.stop_requested:
                LOGGER.info('Translation-only pipeline stopped by user')
                break

            blk_list = self.imgtrans_proj.pages.get(imgname, [])
            if len(blk_list) > 0:
                self._translate_textblocks(imgname, blk_list)
            self.translate_counter += 1
            self.imgtrans_proj.update_page_progress(imgname, RunStatus.FIN_TRANSLATE)
            self.update_translate_progress.emit(self.translate_counter)

        if self.stop_requested:
            self.pipeline_stopped.emit()

    def _review_pipeline(self):
        self.detect_counter = 0
        self.ocr_counter = 0
        self.translate_counter = 0
        self.inpaint_counter = 0
        self.decensor_counter = 0

        all_pages = list(self.imgtrans_proj.pages.keys())
        pages_to_iterate = self.imgtrans_proj.pipeline_pages(self.pages_to_process, skip_ignored=True)

        self.num_pages = max(1, len(pages_to_iterate))
        for process_idx, page_name in enumerate(pages_to_iterate):
            self.process_idx_to_page_idx[process_idx] = all_pages.index(page_name)

        self.translate_thread.num_process_pages = self.num_pages
        LOGGER.info(f'Running LLM translation review for {len(pages_to_iterate)} pages')

        for imgname in pages_to_iterate:
            if self.stop_requested:
                LOGGER.info('LLM translation review stopped by user')
                break

            blk_list = self.imgtrans_proj.pages.get(imgname, [])
            if len(blk_list) > 0:
                self._review_textblocks(imgname, blk_list)
            self.translate_counter += 1
            self.imgtrans_proj.update_page_progress(imgname, RunStatus.FIN_TRANSLATE)
            self.update_translate_progress.emit(self.translate_counter)

        if self.stop_requested:
            self.pipeline_stopped.emit()

    def _decensor_pipeline(self):
        self.detect_counter = 0
        self.ocr_counter = 0
        self.translate_counter = 0
        self.inpaint_counter = 0
        self.decensor_counter = 0
        pages_to_iterate = self._iter_pipeline_pages(skip_ignored=False)
        self.inpaint_thread.num_process_pages = self.num_pages
        LOGGER.info(f'Running decensor for {len(pages_to_iterate)} pages')
        self._run_decensor_pages(pages_to_iterate)

        if self.stop_requested:
            self.pipeline_stopped.emit()

    def detect_finished(self) -> bool:
        if self.imgtrans_proj is None:
            return True
        return self.detect_counter == self.num_pages or not cfg_module.enable_detect

    def ocr_finished(self) -> bool:
        if self.imgtrans_proj is None:
            return True
        return self.ocr_counter == self.num_pages or not cfg_module.enable_ocr

    def translate_finished(self) -> bool:
        if self.translation_only:
            return self.translate_counter == self.num_pages
        if self.review_only:
            return self.translate_counter == self.num_pages
        if self.imgtrans_proj is None or not cfg_module.enable_translate:
            return True
        if self.parallel_trans:
            # 检查翻译计数器是否达到需要处理的页面数
            return self.translate_thread.finished_counter >= self.num_pages
        return self.translate_counter == self.num_pages or not cfg_module.enable_translate

    def inpaint_finished(self) -> bool:
        if self.inpaint_optimization_only:
            return self.inpaint_counter == self.num_pages
        if self.imgtrans_proj is None or not cfg_module.enable_inpaint:
            return True
        return self.inpaint_counter == self.num_pages or not cfg_module.enable_inpaint

    def decensor_finished(self) -> bool:
        if self.imgtrans_proj is None:
            return True
        if self.decensor_only:
            return self.decensor_counter == self.num_pages
        return True

    def run(self):
        if self.job is not None:
            self.job()
        self.job = None

    def recent_finished_index(self, ref_counter: int) -> int:
        if self.translation_only or self.decensor_only or self.inpaint_optimization_only:
            process_idx = ref_counter - 1
            if hasattr(self, 'process_idx_to_page_idx') and process_idx in self.process_idx_to_page_idx:
                return self.process_idx_to_page_idx[process_idx]
            return process_idx
        if cfg_module.enable_detect:
            ref_counter = min(ref_counter, self.detect_counter)
        if cfg_module.enable_ocr:
            ref_counter = min(ref_counter, self.ocr_counter)
        if cfg_module.enable_inpaint:
            ref_counter = min(ref_counter, self.inpaint_counter)
        if cfg_module.enable_translate:
            if self.parallel_trans:
                ref_counter = min(ref_counter, self.translate_thread.finished_counter)
            else:
                ref_counter = min(ref_counter, self.translate_counter)
        process_idx = ref_counter - 1
        # 将处理索引转换为实际页面索引
        if hasattr(self, 'process_idx_to_page_idx') and process_idx in self.process_idx_to_page_idx:
            return self.process_idx_to_page_idx[process_idx]
        return process_idx


def unload_modules(self, module_names):
    model_deleted = False
    for module in module_names:
        module: BaseModule = getattr(self, module)
        model_deleted = model_deleted or module.unload_model()
    if model_deleted:
        soft_empty_cache()


class ModuleManager(QObject):
    imgtrans_proj: ProjImgTrans = None

    finish_translate_page = Signal(str)
    canvas_inpaint_finished = Signal(dict)
    inpaint_th_finished = Signal()

    imgtrans_pipeline_finished = Signal()
    blktrans_pipeline_finished = Signal(int, list)
    page_trans_finished = Signal(int)
    page_decensor_finished = Signal(int)

    run_canvas_inpaint = False
    is_waiting_th = False
    block_set_inpainter = False

    def __init__(self, 
                 imgtrans_proj: ProjImgTrans,
                 *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.imgtrans_proj = imgtrans_proj
        self.check_inpaint_fin_timer = QTimer(self)
        self.check_inpaint_fin_timer.timeout.connect(self.check_inpaint_th_finished)
        self.pipeline_pages_to_process = None
        self.post_pipeline_merge_done = False
        self.active_pipeline_history_id = None
        self.active_pipeline_started_at = None

    def setupThread(self, config_panel: ConfigPanel, imgtrans_progress_msgbox: ImgtransProgressMessageBox, ocr_postprocess: Callable = None, translate_preprocess: Callable = None, translate_postprocess: Callable = None):
        self.textdetect_thread = TextDetectThread()

        self.ocr_thread = OCRThread()
        
        self.translate_thread = TranslateThread()
        self.translate_thread.progress_changed.connect(self.on_update_translate_progress)
        self.translate_thread.finish_translate_page.connect(self.on_finish_translate_page)  

        self.inpaint_thread = InpaintThread()
        self.inpaint_thread.finish_inpaint.connect(self.on_finish_inpaint)

        self.progress_msgbox = imgtrans_progress_msgbox
        self.progress_msgbox.stop_clicked.connect(self.stopImgtransPipeline)
        self.progress_msgbox.force_stop_clicked.connect(self.forceStopImgtransPipeline)

        self.imgtrans_thread = ImgtransThread(self.textdetect_thread, self.ocr_thread, self.translate_thread, self.inpaint_thread)
        self.imgtrans_thread.update_detect_progress.connect(self.on_update_detect_progress)
        self.imgtrans_thread.update_ocr_progress.connect(self.on_update_ocr_progress)
        self.imgtrans_thread.update_translate_progress.connect(self.on_update_translate_progress)
        self.imgtrans_thread.update_inpaint_progress.connect(self.on_update_inpaint_progress)
        self.imgtrans_thread.update_decensor_progress.connect(self.on_update_decensor_progress)
        self.imgtrans_thread.finish_blktrans_stage.connect(self.on_finish_blktrans_stage)
        self.imgtrans_thread.finish_blktrans.connect(self.on_finish_blktrans)
        self.imgtrans_thread.pipeline_stopped.connect(self.on_imgtrans_thread_stopped)
        self.imgtrans_thread.finished.connect(self.on_imgtrans_thread_finished)

        self.translator_panel = translator_panel = config_panel.trans_config_panel        
        translator_params = merge_config_module_params(cfg_module.translator_params, GET_VALID_TRANSLATORS(), TRANSLATORS.get)
        translator_panel.addModulesParamWidgets(translator_params)
        translator_panel.translator_changed.connect(self.setTranslator)
        translator_panel.paramwidget_edited.connect(self.on_translatorparam_edited)
        translator_panel.translateByTextblockBox.checker_changed.connect(self.on_translatebyblock_checker_changed)
        translator_panel.translateByTextblockBox.checker.setChecked(cfg_module.translate_by_textblock)

        from modules.translators.hooks import chs2cht
        BaseTranslator.register_preprocess_hooks({'keyword_sub': translate_preprocess})
        BaseTranslator.register_postprocess_hooks({'chs2cht': chs2cht, 'keyword_sub': translate_postprocess})

        self.inpaint_panel = inpainter_panel = config_panel.inpaint_config_panel
        inpainter_params = merge_config_module_params(cfg_module.inpainter_params, GET_VALID_INPAINTERS(), INPAINTERS.get)
        inpainter_panel.addModulesParamWidgets(inpainter_params)
        inpainter_panel.paramwidget_edited.connect(self.on_inpainterparam_edited)
        inpainter_panel.inpainter_changed.connect(self.setInpainter)
        inpainter_panel.needInpaintChecker.checker_changed.connect(self.on_inpainter_checker_changed)
        inpainter_panel.needInpaintChecker.checker.setChecked(cfg_module.check_need_inpaint)

        self.textdetect_panel = textdetector_panel = config_panel.detect_config_panel
        textdetector_params = merge_config_module_params(cfg_module.textdetector_params, GET_VALID_TEXTDETECTORS(), TEXTDETECTORS.get)
        textdetector_panel.addModulesParamWidgets(textdetector_params)
        textdetector_panel.paramwidget_edited.connect(self.on_textdetectorparam_edited)
        textdetector_panel.detector_changed.connect(self.setTextDetector)

        self.ocr_panel = ocr_panel = config_panel.ocr_config_panel
        ocr_params = merge_config_module_params(cfg_module.ocr_params, GET_VALID_OCR(), OCR.get)
        ocr_panel.addModulesParamWidgets(ocr_params)
        ocr_panel.paramwidget_edited.connect(self.on_ocrparam_edited)
        ocr_panel.ocr_changed.connect(self.setOCR)
        OCRBase.register_postprocess_hooks(ocr_postprocess)

        config_panel.unload_models.connect(self.unload_all_models)


    def unload_all_models(self):
        unload_modules(self, {'textdetector', 'inpainter', 'ocr', 'translator'})

    @property
    def translator(self) -> BaseTranslator:
        return self.translate_thread.translator

    @property
    def inpainter(self) -> InpainterBase:
        return self.inpaint_thread.inpainter

    @property
    def textdetector(self) -> TextDetectorBase:
        return self.textdetect_thread.textdetector

    @property
    def ocr(self) -> OCRBase:
        return self.ocr_thread.ocr

    def translatePage(self, run_target: bool, page_key: str):
        if not run_target:
            if self.translate_thread.isRunning():
                LOGGER.warning('Terminating a running translation thread.')
                self.translate_thread.terminate()
            return
        self.translate_thread.translatePage(self.imgtrans_proj.pages, page_key, self.imgtrans_proj)

    def inpainterBusy(self):
        return self.inpaint_thread.isRunning()

    def inpaint(self, img: np.ndarray, mask: np.ndarray, img_key: str = None, inpaint_rect = None, **kwargs):
        if self.inpaint_thread.isRunning():
            LOGGER.warning('Waiting for inpainting to finish')
            return
        self.inpaint_thread.inpaint(img, mask, img_key, inpaint_rect, **kwargs)

    def terminateRunningThread(self):
        if self.textdetect_thread.isRunning():
            self.textdetect_thread.quit()
        if self.ocr_thread.isRunning():
            self.ocr_thread.quit()
        if self.inpaint_thread.isRunning():
            self.inpaint_thread.quit()
        if self.translate_thread.isRunning():
            self.translate_thread.quit()

    def _module_history_info(self, module: BaseModule) -> Dict:
        if module is None:
            return {}
        info = {'name': getattr(module, 'name', module.__class__.__name__)}
        params = getattr(module, 'params', None) or {}
        for key in [
            'provider',
            'model',
            'override model',
            'endpoint',
            'version',
            'device',
            'reasoning',
            'reasoning level',
        ]:
            if key not in params:
                continue
            try:
                value = module.get_param_value(key)
            except Exception:
                continue
            if key == 'override model' and not value:
                continue
            info[key.replace(' ', '_')] = value
        if 'model' in info and 'override_model' in info:
            info['effective_model'] = info['override_model']
        elif 'model' in info:
            info['effective_model'] = info['model']
        return info

    def _pipeline_history_modules(self) -> Dict:
        return {
            'textdetector': self._module_history_info(self.textdetector),
            'ocr': self._module_history_info(self.ocr),
            'translator': self._module_history_info(self.translator),
            'inpainter': self._module_history_info(self.inpainter),
        }

    @staticmethod
    def _pipeline_history_stages(pipeline_name: str) -> Dict:
        if pipeline_name in {'translation_only_pipeline', 'llm_review_pipeline'}:
            return {
                'detect': False,
                'ocr': False,
                'translate': True,
                'inpaint': False,
                'inpaint_optimization': False,
            }
        if pipeline_name == 'inpaint_optimization_pipeline':
            return {
                'detect': False,
                'ocr': False,
                'translate': False,
                'inpaint': True,
                'inpaint_optimization': True,
            }
        return {
            'detect': bool(cfg_module.enable_detect),
            'ocr': bool(cfg_module.enable_ocr),
            'translate': bool(cfg_module.enable_translate),
            'inpaint': bool(cfg_module.enable_inpaint),
            'inpaint_optimization': bool(cfg_module.enable_inpaint_optimization),
        }

    @staticmethod
    def _pipeline_history_steps(stages: Dict, modules: Dict) -> List[Dict]:
        definitions = [
            ('text_detection', 'Text Detection', 'detect', 'textdetector'),
            ('ocr', 'OCR', 'ocr', 'ocr'),
            ('translate', 'Translate', 'translate', 'translator'),
            ('inpaint', 'Inpaint', 'inpaint', 'inpainter'),
        ]
        return [
            {
                'step': step,
                'label': label,
                'enabled': bool(stages.get(stage_key)),
                'status': 'running' if stages.get(stage_key) else 'skipped',
                'module': modules.get(module_key, {}),
            }
            for step, label, stage_key, module_key in definitions
        ]

    def _start_pipeline_history(self, pipeline_name: str, pages_to_process, process_pages: List[str]):
        self.active_pipeline_started_at = time.time()
        stages = self._pipeline_history_stages(pipeline_name)
        modules = self._pipeline_history_modules()
        entry = {
            'pipeline': pipeline_name,
            'process': pipeline_name,
            'status': 'running',
            'started_at': ProjImgTrans.utc_now_iso(),
            'duration_seconds': None,
            'page_count': len(process_pages),
            'pages_requested': list(pages_to_process) if pages_to_process else None,
            'pages_processed': list(process_pages),
            'stages': stages,
            'modules': modules,
            'steps': self._pipeline_history_steps(stages, modules),
        }
        self.active_pipeline_history_id = self.imgtrans_proj.append_pipeline_history(entry)
        LOGGER.info(f'Pipeline history started: {pipeline_name} ({self.active_pipeline_history_id})')

    def _finish_pipeline_history(self, status: str):
        if not self.active_pipeline_history_id:
            return
        started_at = self.active_pipeline_started_at or time.time()
        modules = self._pipeline_history_modules()
        stages = self._pipeline_history_stages('')
        history = self.imgtrans_proj.load_pipeline_history()
        for entry in reversed(history.get('entries', [])):
            if entry.get('id') == self.active_pipeline_history_id:
                stages = entry.get('stages', stages)
                break
        steps = self._pipeline_history_steps(stages, modules)
        for step in steps:
            if step['enabled']:
                step['status'] = status
        updates = {
            'status': status,
            'finished_at': ProjImgTrans.utc_now_iso(),
            'duration_seconds': round(max(0.0, time.time() - started_at), 3),
            'modules': modules,
            'steps': steps,
        }
        if self.imgtrans_proj.update_pipeline_history_entry(self.active_pipeline_history_id, updates):
            LOGGER.info(
                f'Pipeline history finished: {self.active_pipeline_history_id} '
                f'status={status} duration={updates["duration_seconds"]}s'
            )
        self.active_pipeline_history_id = None
        self.active_pipeline_started_at = None

    def check_inpaint_th_finished(self):
        if self.inpaint_thread.isRunning():
            return
        self.block_set_inpainter = False
        self.check_inpaint_fin_timer.stop()
        self.inpaint_th_finished.emit()

    def runImgtransPipeline(self, pages_to_process=None):
        if self.imgtrans_proj.is_empty:
            LOGGER.info('proj file is empty, nothing to do')
            self.progress_msgbox.hide()
            return
        if cfg_module.skip_cover_title_pages:
            self.imgtrans_proj.update_cover_title_pages()
        process_pages = self.imgtrans_proj.pipeline_pages(pages_to_process, skip_ignored=True)
        if len(process_pages) == 0:
            LOGGER.info('No pages to process after applying ignored page filters')
            self.progress_msgbox.hide()
            self._finish_pipeline_history('completed')
            self.imgtrans_pipeline_finished.emit()
            return
        self._start_pipeline_history('image_translation_pipeline', pages_to_process, process_pages)
        self.last_finished_index = -1
        self.pipeline_pages_to_process = pages_to_process
        self.post_pipeline_merge_done = False
        self.terminateRunningThread()
        
        if cfg_module.all_stages_disabled() and self.imgtrans_proj is not None and self.imgtrans_proj.num_pages > 0:
            for page_name in process_pages:
                self.page_trans_finished.emit(self.imgtrans_proj.pagename2idx(page_name))
            self._finish_pipeline_history('completed')
            self.imgtrans_pipeline_finished.emit()
            return
        
        self.progress_msgbox.detect_bar.setVisible(cfg_module.enable_detect)
        self.progress_msgbox.ocr_bar.setVisible(cfg_module.enable_ocr)
        self.progress_msgbox.translate_bar.setVisible(cfg_module.enable_translate)
        self.progress_msgbox.inpaint_bar.setVisible(cfg_module.enable_inpaint)
        self.progress_msgbox.decensor_bar.setVisible(False)
        self.progress_msgbox.zero_progress()
        self.progress_msgbox.show()
        self.imgtrans_thread.runImgtransPipeline(self.imgtrans_proj, pages_to_process)

    def runTranslateOnlyPipeline(self, pages_to_process=None):
        if self.imgtrans_proj.is_empty:
            LOGGER.info('proj file is empty, nothing to translate')
            self.progress_msgbox.hide()
            return
        if cfg_module.skip_cover_title_pages:
            self.imgtrans_proj.update_cover_title_pages()
        if len(self.imgtrans_proj.pipeline_pages(pages_to_process, skip_ignored=True)) == 0:
            LOGGER.info('No pages to translate after applying ignored page filters')
            self.progress_msgbox.hide()
            self.imgtrans_pipeline_finished.emit()
            return
        process_pages = self.imgtrans_proj.pipeline_pages(pages_to_process, skip_ignored=True)
        self._start_pipeline_history('translation_only_pipeline', pages_to_process, process_pages)
        self.last_finished_index = -1
        self.pipeline_pages_to_process = pages_to_process
        self.post_pipeline_merge_done = False
        self.terminateRunningThread()

        self.progress_msgbox.detect_bar.setVisible(False)
        self.progress_msgbox.ocr_bar.setVisible(False)
        self.progress_msgbox.translate_bar.setVisible(True)
        self.progress_msgbox.inpaint_bar.setVisible(False)
        self.progress_msgbox.decensor_bar.setVisible(False)
        self.progress_msgbox.zero_progress()
        self.progress_msgbox.show()
        self.imgtrans_thread.runTranslateOnlyPipeline(self.imgtrans_proj, pages_to_process)

    def runReviewPipeline(self, pages_to_process=None):
        if self.imgtrans_proj.is_empty:
            LOGGER.info('proj file is empty, nothing to review')
            self.progress_msgbox.hide()
            return
        if (
            self.translator is None
            or not hasattr(self.translator, 'supports_translation_review')
            or not self.translator.supports_translation_review()
        ):
            LOGGER.info('Current translator does not support LLM review')
            self.progress_msgbox.hide()
            self.imgtrans_pipeline_finished.emit()
            return
        if cfg_module.skip_cover_title_pages:
            self.imgtrans_proj.update_cover_title_pages()
        if len(self.imgtrans_proj.pipeline_pages(pages_to_process, skip_ignored=True)) == 0:
            LOGGER.info('No pages to review after applying ignored page filters')
            self.progress_msgbox.hide()
            self.imgtrans_pipeline_finished.emit()
            return
        process_pages = self.imgtrans_proj.pipeline_pages(pages_to_process, skip_ignored=True)
        self._start_pipeline_history('llm_review_pipeline', pages_to_process, process_pages)
        self.last_finished_index = -1
        self.pipeline_pages_to_process = pages_to_process
        self.post_pipeline_merge_done = False
        self.terminateRunningThread()

        self.progress_msgbox.detect_bar.setVisible(False)
        self.progress_msgbox.ocr_bar.setVisible(False)
        self.progress_msgbox.translate_bar.setVisible(True)
        self.progress_msgbox.inpaint_bar.setVisible(False)
        self.progress_msgbox.decensor_bar.setVisible(False)
        self.progress_msgbox.zero_progress()
        self.progress_msgbox.show()
        self.imgtrans_thread.runReviewPipeline(self.imgtrans_proj, pages_to_process)

    def runDecensorPipeline(self, pages_to_process=None):
        if self.imgtrans_proj.is_empty:
            LOGGER.info('proj file is empty, nothing to decensor')
            self.progress_msgbox.hide()
            return
        if self.anyPipelineThreadRunning():
            LOGGER.warning('Stopping existing pipeline before starting decensor.')
            self.forceStopImgtransPipeline(emit_finished=False)
        process_pages = self.imgtrans_proj.pipeline_pages(pages_to_process, skip_ignored=False)
        self._start_pipeline_history('decensor_pipeline', pages_to_process, process_pages)
        self.last_finished_index = -1
        self.pipeline_pages_to_process = pages_to_process
        self.post_pipeline_merge_done = False
        self.terminateRunningThread()

        self.progress_msgbox.detect_bar.setVisible(False)
        self.progress_msgbox.ocr_bar.setVisible(False)
        self.progress_msgbox.translate_bar.setVisible(False)
        self.progress_msgbox.inpaint_bar.setVisible(False)
        self.progress_msgbox.decensor_bar.setVisible(True)
        self.progress_msgbox.zero_progress()
        self.progress_msgbox.show()
        self.imgtrans_thread.runDecensorPipeline(self.imgtrans_proj, pages_to_process)

    def runInpaintOptimizationPipeline(self, pages_to_process=None):
        if self.imgtrans_proj.is_empty:
            LOGGER.info('proj file is empty, nothing to optimize')
            self.progress_msgbox.hide()
            return
        if self.textdetector is None or self.inpainter is None:
            LOGGER.info('Inpaint optimization requires a loaded text detector and inpainter')
            self.progress_msgbox.hide()
            self.imgtrans_pipeline_finished.emit()
            return
        if cfg_module.skip_cover_title_pages:
            self.imgtrans_proj.update_cover_title_pages()
        if len(self.imgtrans_proj.pipeline_pages(pages_to_process, skip_ignored=True)) == 0:
            LOGGER.info('No pages to optimize after applying ignored page filters')
            self.progress_msgbox.hide()
            self.imgtrans_pipeline_finished.emit()
            return
        if self.anyPipelineThreadRunning():
            LOGGER.warning('Stopping existing pipeline before starting inpaint optimization.')
            self.forceStopImgtransPipeline(emit_finished=False)
        process_pages = self.imgtrans_proj.pipeline_pages(pages_to_process, skip_ignored=True)
        self._start_pipeline_history('inpaint_optimization_pipeline', pages_to_process, process_pages)
        self.last_finished_index = -1
        self.pipeline_pages_to_process = pages_to_process
        self.post_pipeline_merge_done = False
        self.terminateRunningThread()

        self.progress_msgbox.detect_bar.setVisible(False)
        self.progress_msgbox.ocr_bar.setVisible(False)
        self.progress_msgbox.translate_bar.setVisible(False)
        self.progress_msgbox.inpaint_bar.setVisible(True)
        self.progress_msgbox.decensor_bar.setVisible(False)
        self.progress_msgbox.zero_progress()
        self.progress_msgbox.show()
        self.imgtrans_thread.runInpaintOptimizationPipeline(self.imgtrans_proj, pages_to_process)
    
    def stopImgtransPipeline(self):
        """停止图像翻译流程"""
        if self.run_canvas_inpaint and self.inpaint_thread.isRunning():
            LOGGER.info('Stopping canvas inpainting operation...')
            self.forceStopImgtransPipeline(emit_finished=False)
            return
        LOGGER.info('Stopping image translation pipeline...')
        self.imgtrans_thread.requestStop()

    def anyPipelineThreadRunning(self) -> bool:
        return any(
            thread.isRunning()
            for thread in [
                self.imgtrans_thread,
                self.translate_thread,
                self.textdetect_thread,
                self.ocr_thread,
                self.inpaint_thread,
            ]
        )

    def _force_terminate_thread(self, thread: QThread, thread_name: str):
        if thread is None or not thread.isRunning():
            return
        LOGGER.warning(f'Force stopping {thread_name} thread.')
        try:
            if hasattr(thread, 'requestStop'):
                thread.requestStop()
        except Exception as e:
            LOGGER.warning(f'Failed to request stop for {thread_name}: {e}')
        thread.terminate()
        if not thread.wait(1500):
            LOGGER.warning(f'{thread_name} thread did not finish after force stop.')

    def forceStopImgtransPipeline(self, emit_finished: bool = True):
        """Forcefully terminate all running pipeline and translation threads."""
        LOGGER.warning('Force stopping image translation pipeline and translation process.')
        was_canvas_inpaint = self.run_canvas_inpaint
        for thread, name in [
            (self.translate_thread, 'translator'),
            (self.textdetect_thread, 'text detection'),
            (self.ocr_thread, 'OCR'),
            (self.inpaint_thread, 'inpainting'),
            (self.imgtrans_thread, 'pipeline'),
        ]:
            self._force_terminate_thread(thread, name)

        self.imgtrans_thread.stop_requested = False
        self.translate_thread.stop_requested = False
        self.imgtrans_thread.translation_only = False
        self.imgtrans_thread.review_only = False
        self.imgtrans_thread.decensor_only = False
        self.imgtrans_thread.pipeline_pagekey_queue.clear()
        self.translate_thread.pipeline_pagekey_queue.clear()
        self.run_canvas_inpaint = False
        self.inpaint_thread.inpainting = False
        self.block_set_inpainter = False
        self.progress_msgbox.hide()
        self._finish_pipeline_history('force_stopped')
        if was_canvas_inpaint:
            self.inpaint_thread.inpaint_failed.emit()
        if emit_finished:
            self.imgtrans_pipeline_finished.emit()

    def runBlktransPipeline(self, blk_list: List[TextBlock], tgt_img: np.ndarray, mode: int, blk_ids: List[int], tgt_mask):
        self.terminateRunningThread()
        self.progress_msgbox.hide_all_bars()
        if mode >= 0 and mode < 3:
            self.progress_msgbox.ocr_bar.show()
        if mode >= 2:
            self.progress_msgbox.inpaint_bar.show()
        if mode in (-3, -2) or (mode != 0 and mode < 3):
            self.progress_msgbox.translate_bar.show()
        self.progress_msgbox.zero_progress()
        self.progress_msgbox.show()
        page_key = self.imgtrans_proj.current_img if self.imgtrans_proj is not None else None
        self.imgtrans_thread.runBlktransPipeline(blk_list, tgt_img, mode, blk_ids, tgt_mask, page_key)

    def on_finish_blktrans_stage(self, stage: str, progress: int):
        if stage == 'ocr':
            self.progress_msgbox.updateOCRProgress(progress)
        elif stage == 'translate':
            self.progress_msgbox.updateTranslateProgress(progress)
        elif stage == 'inpaint':
            self.progress_msgbox.updateInpaintProgress(progress)
        else:
            raise NotImplementedError(f'Unknown stage: {stage}')
        
    def on_finish_blktrans(self, mode: int, blk_ids: List):
        self.blktrans_pipeline_finished.emit(mode, blk_ids)
        self.progress_msgbox.hide()

    def on_update_detect_progress(self, progress: int):
        ri = self.imgtrans_thread.recent_finished_index(progress)
        if 'detect' in shared.pbar:
            shared.pbar['detect'].update(1)
        progress = int(progress / self.imgtrans_thread.num_pages * 100)
        self.progress_msgbox.updateDetectProgress(progress)
        if ri != self.last_finished_index:
            self.last_finished_index = ri
            self.page_trans_finished.emit(ri)
        if progress == 100:
            self.finishImgtransPipeline()

    def on_update_ocr_progress(self, progress: int):
        ri = self.imgtrans_thread.recent_finished_index(progress)
        if 'ocr' in shared.pbar:
            shared.pbar['ocr'].update(1)
        progress = int(progress / self.imgtrans_thread.num_pages * 100)
        self.progress_msgbox.updateOCRProgress(progress)
        if ri != self.last_finished_index:
            self.last_finished_index = ri
            self.page_trans_finished.emit(ri)
        if progress == 100:
            self.finishImgtransPipeline()

    def on_update_translate_progress(self, progress: int):
        ri = self.imgtrans_thread.recent_finished_index(progress)
        if 'translate' in shared.pbar:
            shared.pbar['translate'].update(1)
        progress = int(progress / self.imgtrans_thread.num_pages * 100)
        self.progress_msgbox.updateTranslateProgress(progress)
        if ri != self.last_finished_index:
            self.last_finished_index = ri
            self.page_trans_finished.emit(ri)
        if progress == 100:
            self.finishImgtransPipeline()

    def on_update_inpaint_progress(self, progress: int):
        ri = self.imgtrans_thread.recent_finished_index(progress)
        if 'inpaint' in shared.pbar:
            shared.pbar['inpaint'].update(1)
        progress = int(progress / self.imgtrans_thread.num_pages * 100)
        self.progress_msgbox.updateInpaintProgress(progress)
        if ri != self.last_finished_index:
            self.last_finished_index = ri
            if self.imgtrans_thread.inpaint_optimization_only:
                self.page_decensor_finished.emit(ri)
            else:
                self.page_trans_finished.emit(ri)
        if progress == 100:
            self.finishImgtransPipeline()

    def on_update_decensor_progress(self, progress: int):
        ri = self.imgtrans_thread.recent_finished_index(progress)
        progress = int(progress / self.imgtrans_thread.num_pages * 100)
        self.progress_msgbox.updateDecensorProgress(progress)
        if ri != self.last_finished_index:
            self.last_finished_index = ri
            self.page_decensor_finished.emit(ri)
        if progress == 100:
            self.finishImgtransPipeline()

    def progress(self):
        progress = {}
        num_pages = self.imgtrans_thread.num_pages
        if cfg_module.enable_detect:
            progress['detect'] = self.imgtrans_thread.detect_counter / num_pages
        if cfg_module.enable_ocr:
            progress['ocr'] = self.imgtrans_thread.ocr_counter / num_pages
        if cfg_module.enable_inpaint:
            progress['inpaint'] = self.imgtrans_thread.inpaint_counter / num_pages
        if cfg_module.enable_translate:
            progress['translate'] = self.imgtrans_thread.translate_counter / num_pages
        if self.imgtrans_thread.decensor_only:
            progress['decensor'] = self.imgtrans_thread.decensor_counter / num_pages
        return progress

    def proj_finished(self):
        if self.imgtrans_thread.decensor_only:
            return self.imgtrans_thread.decensor_finished()
        if self.imgtrans_thread.inpaint_optimization_only:
            return self.imgtrans_thread.inpaint_finished()
        if self.imgtrans_thread.translation_only or self.imgtrans_thread.review_only:
            return self.imgtrans_thread.translate_finished()
        if self.imgtrans_thread.detect_finished() \
            and self.imgtrans_thread.ocr_finished() \
                and self.imgtrans_thread.translate_finished() \
                    and self.imgtrans_thread.inpaint_finished() \
                        and self.imgtrans_thread.decensor_finished():
            return True
        return False

    def post_merge_config_from_settings(self) -> Dict:
        return {
            "MERGE_MODE": pcfg.module.post_merge_mode,
            "READING_DIRECTION": "LTR",
            "PER_LABEL_DIRECTIONS": {},
            "LABELS_TO_EXCLUDE_FROM_MERGE": set(),
            "LABEL_MERGE_STRATEGY": "PREFER_SHORTER",
            "REQUIRE_SAME_LABEL": False,
            "USE_SPECIFIC_MERGE_GROUPS": False,
            "SPECIFIC_MERGE_GROUPS": [],
            "VERTICAL_MERGE_PARAMS": {
                "max_vertical_gap": pcfg.module.post_merge_max_vertical_gap,
                "min_width_overlap_ratio": pcfg.module.post_merge_min_width_overlap_ratio,
                "overlap_epsilon": 1e-6,
            },
            "HORIZONTAL_MERGE_PARAMS": {
                "max_horizontal_gap": pcfg.module.post_merge_max_horizontal_gap,
                "min_height_overlap_ratio": pcfg.module.post_merge_min_height_overlap_ratio,
                "overlap_epsilon": 1e-6,
            },
            "ADVANCED_MERGE_OPTIONS": {
                "allow_negative_gap": True,
                "debug_mode": False,
            },
            "OUTPUT_SHAPE_TYPE": "rectangle",
        }

    def _merge_shapes_by_mode(self, shapes: List[dict], config: Dict):
        from utils import merger

        mode = config.get("MERGE_MODE", "NONE")
        total_merged = 0
        if mode == "VERTICAL":
            final_shapes, total_merged = merger.perform_merge(shapes, "VERTICAL", config)
        elif mode == "HORIZONTAL":
            final_shapes, total_merged = merger.perform_merge(shapes, "HORIZONTAL", config)
        elif mode == "VERTICAL_THEN_HORIZONTAL":
            temp, count1 = merger.perform_merge(shapes, "VERTICAL", config)
            final_shapes, count2 = merger.perform_merge(temp, "HORIZONTAL", config)
            total_merged = count1 + count2
        elif mode == "HORIZONTAL_THEN_VERTICAL":
            temp, count1 = merger.perform_merge(shapes, "HORIZONTAL", config)
            final_shapes, count2 = merger.perform_merge(temp, "VERTICAL", config)
            total_merged = count1 + count2
        else:
            final_shapes = shapes
        return final_shapes, total_merged

    def apply_post_pipeline_textbox_merge(self):
        if self.post_pipeline_merge_done or not pcfg.module.post_merge_textboxes:
            return

        self.post_pipeline_merge_done = True
        all_pages = list(self.imgtrans_proj.pages.keys())
        if self.pipeline_pages_to_process:
            page_names = self.imgtrans_proj.pipeline_pages(self.pipeline_pages_to_process, skip_ignored=True)
        else:
            page_names = self.imgtrans_proj.pipeline_pages(skip_ignored=True)

        if not page_names:
            return

        config = self.post_merge_config_from_settings()
        changed_page_indices = []
        total_merged = 0
        for page_name in page_names:
            blocks = self.imgtrans_proj.pages.get(page_name, [])
            if len(blocks) < 2:
                continue

            try:
                shapes = [blk.to_dict(deep_copy=True) for blk in blocks]
                final_shapes, merged_count = self._merge_shapes_by_mode(shapes, config)
                if merged_count > 0:
                    self.imgtrans_proj.pages[page_name] = [
                        TextBlock(**shape) for shape in final_shapes
                    ]
                    total_merged += merged_count
                    changed_page_indices.append(all_pages.index(page_name))
            except Exception as e:
                LOGGER.error(f'Post-pipeline text box merge failed for {page_name}: {e}')

        if total_merged > 0:
            LOGGER.info(f'Post-pipeline text box merge reduced {total_merged} boxes.')
            for page_index in changed_page_indices:
                self.page_trans_finished.emit(page_index)

    def finishImgtransPipeline(self):
        if self.proj_finished():
            if not self.imgtrans_thread.translation_only and not self.imgtrans_thread.review_only:
                self.apply_post_pipeline_textbox_merge()
            self.progress_msgbox.hide()
            self._finish_pipeline_history('completed')
            self.imgtrans_pipeline_finished.emit()
            self.imgtrans_thread.translation_only = False
            self.imgtrans_thread.review_only = False
            self.imgtrans_thread.decensor_only = False
            self.imgtrans_thread.inpaint_optimization_only = False
    
    def on_imgtrans_thread_stopped(self):
        """线程完成时确保关闭进度对话框"""
        # 线程完成了，直接关闭窗口
        self.progress_msgbox.hide()
        self._finish_pipeline_history('stopped')
        self.imgtrans_pipeline_finished.emit()
        self.imgtrans_thread.translation_only = False
        self.imgtrans_thread.review_only = False
        self.imgtrans_thread.decensor_only = False
        self.imgtrans_thread.inpaint_optimization_only = False

    def on_imgtrans_thread_finished(self):
        if self.active_pipeline_history_id:
            self._finish_pipeline_history('failed')

    def setTranslator(self, translator: str = None):
        if translator is None:
            translator = cfg_module.translator
        if self.translate_thread.isRunning():
            LOGGER.warning('Terminating a running translation thread.')
            self.translate_thread.terminate()
        self.translate_thread.setTranslator(translator)

    def setInpainter(self, inpainter: str = None):
        
        if self.block_set_inpainter:
            return
        
        if inpainter is None:
            inpainter =cfg_module.inpainter
        
        if self.inpaint_thread.isRunning():
            self.block_set_inpainter = True
            create_info_dialog(self.tr('Set Inpainter...'), modal=True, signal_slot_map_list=[{'signal': self.inpaint_th_finished, 'slot': 'done'}])
            self.check_inpaint_fin_timer.start(300)
            return

        self.inpaint_thread.setInpainter(inpainter)

    def setTextDetector(self, textdetector: str = None):
        if textdetector is None:
            textdetector = cfg_module.textdetector
        if self.textdetect_thread.isRunning():
            LOGGER.warning('Terminating a running text detection thread.')
            self.textdetect_thread.terminate()
        self.textdetect_thread.setTextDetector(textdetector)

    def setOCR(self, ocr: str = None):
        if ocr is None:
            ocr = cfg_module.ocr
        if self.ocr_thread.isRunning():
            LOGGER.warning('Terminating a running OCR thread.')
            self.ocr_thread.terminate()
        self.ocr_thread.setOCR(ocr)

    def setOCRFallback(self, ocr: str = ''):
        self.imgtrans_thread.configure_ocr_fallback(ocr)

    def on_finish_translate_page(self, page_key: str):
        self.finish_translate_page.emit(page_key)
    
    def on_finish_inpaint(self, inpaint_dict: dict):
        if self.run_canvas_inpaint:
            self.canvas_inpaint_finished.emit(inpaint_dict)
            self.run_canvas_inpaint = False

    def canvas_inpaint(self, inpaint_dict):
        self.run_canvas_inpaint = True
        self.inpaint(**inpaint_dict)
    
    def on_translatorparam_edited(self, param_key: str, param_content: dict):
        selected_translator = self.translator_panel.module_combobox.currentText()
        if self.translator is not None and self.translator.name == selected_translator:
            self.updateModuleSetupParam(self.translator, param_key, param_content)
            cfg_module.translator_params[self.translator.name] = self.translator.params
        elif (
            selected_translator in cfg_module.translator_params
            and not param_content.get('flush', False)
            and not param_content.get('select_path', False)
        ):
            params = cfg_module.translator_params[selected_translator]
            if params is not None and param_key in params:
                value = params[param_key]
                content = param_content['content']
                if isinstance(value, dict):
                    try:
                        value_type = value.get('data_type', type(value['value']))
                        content = value_type(content)
                    except (TypeError, ValueError):
                        LOGGER.warning(
                            f'Invalid param value {content} for {selected_translator}.{param_key}'
                        )
                    value['value'] = content
                else:
                    try:
                        params[param_key] = type(value)(content)
                    except (TypeError, ValueError):
                        LOGGER.warning(
                            f'Invalid param value {content} for {selected_translator}.{param_key}'
                        )

    def on_inpainterparam_edited(self, param_key: str, param_content: dict):
        if self.inpainter is not None:
            self.updateModuleSetupParam(self.inpainter, param_key, param_content)
            cfg_module.inpainter_params[self.inpainter.name] = self.inpainter.params

    def on_textdetectorparam_edited(self, param_key: str, param_content: dict):
        if self.textdetector is not None:
            self.updateModuleSetupParam(self.textdetector, param_key, param_content)
            cfg_module.textdetector_params[self.textdetector.name] = self.textdetector.params

    def on_ocrparam_edited(self, param_key: str, param_content: dict):
        if self.ocr is not None:
            self.updateModuleSetupParam(self.ocr, param_key, param_content)
            cfg_module.ocr_params[self.ocr.name] = self.ocr.params

    def updateModuleSetupParam(self, 
                               module: Union[InpainterBase, BaseTranslator],
                               param_key: str, param_content: dict):
            
        if param_content.get('flush', False):
            param_widget: ParamComboBox = param_content['widget']
            param_widget.blockSignals(True)
            current_item = param_widget.currentText()
            param_widget.clear()
            param_widget.addItems(module.flush(param_key))
            param_widget.setCurrentText(current_item)
            param_widget.blockSignals(False)
        elif param_content.get('select_path', False):
            dialog = QFileDialog()
            f = module.params[param_key].get('path_filter', None)
            p = dialog.getOpenFileUrl(self.parent(), filter=f)[0].toLocalFile()
            if osp.exists(p):
                param_widget: ParamComboBox = param_content['widget']
                param_widget.setCurrentText(p)
        else:
            module.updateParam(param_key, param_content['content'])

    def handle_page_changed(self):
        if not self.imgtrans_thread.isRunning():
            if self.inpaint_thread.inpainting:
                self.run_canvas_inpaint = False
                self.inpaint_thread.terminate()

    def on_inpainter_checker_changed(self, is_checked: bool):
        cfg_module.check_need_inpaint = is_checked
        InpainterBase.check_need_inpaint = is_checked

    def on_translatebyblock_checker_changed(self, is_checked: bool):
        cfg_module.translate_by_textblock = is_checked
        BaseTranslator.translate_by_textblock = is_checked
