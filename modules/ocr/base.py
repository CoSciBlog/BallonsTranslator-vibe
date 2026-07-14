from typing import Tuple, List, Dict, Union, Callable
import re
import numpy as np
import cv2
from collections import OrderedDict

from utils.textblock import TextBlock
from utils.registry import Registry
OCR = Registry('OCR')
register_OCR = OCR.register_module

from ..base import BaseModule, DEFAULT_DEVICE, DEVICE_SELECTOR, LOGGER
from utils.ocr_language import ocr_languages_compatible

class OCRBase(BaseModule):

    _postprocess_hooks = OrderedDict()
    _preprocess_hooks = OrderedDict()
    _line_only: bool = False
    supported_ocr_languages = None

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.name = ''
        for key in OCR.module_dict:
            if OCR.module_dict[key] == self.__class__:
                self.name = key
                break

    def run_ocr(self, img: np.ndarray, blk_list: List[TextBlock] = None, *args, **kwargs) -> Union[List[TextBlock], str]:

        if not self.all_model_loaded():
            self.load_model()

        if img.ndim == 3 and img.shape[-1] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)

        if blk_list is None:
            text = self.ocr_img(img)
            return text
        elif isinstance(blk_list, TextBlock):
            blk_list = [blk_list]

        for blk in blk_list:
            if self.name != 'none_ocr':
                blk.text = []
                
        self._ocr_blk_list(img, blk_list, *args, **kwargs)
        for callback_name, callback in self._postprocess_hooks.items():
            callback(textblocks=blk_list, img=img, ocr_module=self)

        return blk_list

    def supports_language(self, source_language: str) -> bool:
        if self.supported_ocr_languages:
            return any(
                ocr_languages_compatible(source_language, language)
                for language in self.supported_ocr_languages
            )

        configured_languages = []
        for key in ('language', 'target_language', 'language_hints'):
            if not self.params or key not in self.params:
                continue
            value = self.get_param_value(key)
            if isinstance(value, (list, tuple, set)):
                configured_languages.extend(value)
            elif isinstance(value, str):
                configured_languages.extend(
                    part.strip() for part in re.split(r'[,;|]', value) if part.strip()
                )
        if not configured_languages:
            return True
        return any(
            ocr_languages_compatible(source_language, language)
            for language in configured_languages
        )

    def _ocr_blk_list(self, img: np.ndarray, blk_list: List[TextBlock], *args, **kwargs) -> None:
        raise NotImplementedError

    def ocr_img(self, img: np.ndarray) -> str:
        raise NotImplementedError
