import numpy as np
import cv2
from typing import Tuple, List

from .base import register_textdetectors, TextDetectorBase, TextBlock, DEFAULT_DEVICE, DEVICE_SELECTOR, ProjImgTrans
from .ctd import CTDModel

CTD_ONNX_PATH = 'data/models/comictextdetector.pt.onnx'
CTD_TORCH_PATH = 'data/models/comictextdetector.pt'

def load_ctd_model(
    model_path,
    device,
    detect_size=1024,
    det_rearrange_max_batches=4,
) -> CTDModel:
    model = CTDModel(
        model_path,
        detect_size=detect_size,
        device=device,
        det_rearrange_max_batches=det_rearrange_max_batches,
    )
    
    return model

@register_textdetectors('ctd')
class ComicTextDetector(TextDetectorBase):

    dependencies = ['torch', 'torchvision', 'einops']

    params = {
        'detect_size': {
            'type': 'selector',
            'options': [
                896, 1024, 1152, 1280, 1408, 1536, 1664, 1792,
                1920, 2048, 2176, 2304, 2432, 2496,
            ],
            'value': 1280,
            'display_name': 'Detect Size',
            'description': (
                'Square input resolution used by the detector. Higher values '
                'can find smaller text but take longer and require more VRAM. '
                'The listed values are compatible with the model stride. CPU '
                'uses the ONNX model at a fixed 1024 px input.'
            ),
        },
        'det_rearrange_max_batches': {
            'type': 'selector',
            'options': [1, 2, 4, 6, 8, 12, 16, 24, 32],
            'value': 4,
            'display_name': 'Max Split Batch Size',
            'description': (
                'Maximum number of square tiles processed together for very '
                'tall or wide pages. Higher values can improve speed but use '
                'more VRAM or RAM; lower this value after an out-of-memory error.'
            ),
        },
        'device': {
            **DEVICE_SELECTOR(),
            'display_name': 'Device',
            'description': (
                'Execution backend. CUDA uses the PyTorch model and honors '
                'Detect Size; CPU uses the ONNX model at a fixed 1024 px input.'
            ),
        },
        'description': (
            'ComicTextDetector locates comic text regions, estimates their '
            'font size, and creates masks for OCR and inpainting.'
        ),
        'font size multiplier': {
            'value': 1.0,
            'display_name': 'Font Size Multiplier',
            'description': (
                'Scales the detected font size used by automatic typesetting. '
                'Use 1.0 to keep the estimated size.'
            ),
        },
        'font size max': {
            'value': -1,
            'display_name': 'Maximum Font Size',
            'description': (
                'Upper limit for detected font sizes. Use -1 to disable the limit.'
            ),
        },
        'font size min': {
            'value': -1,
            'display_name': 'Minimum Font Size',
            'description': (
                'Lower limit for detected font sizes. Use -1 to disable the limit.'
            ),
        },
        'mask dilate size': {
            'value': 3,
            'display_name': 'Mask Dilation Size',
            'description': (
                'Expands the detected text mask by this many pixels before '
                'inpainting. Use 0 to disable dilation; larger values cover '
                'more area around glyph edges.'
            ),
        },
    }
    _load_model_keys = {'model'}
    download_file_list = [
        {
            'url': 'https://huggingface.co/dreMaz/mit_models/resolve/main/comictextdetector.pt',
            'files': 'data/models/comictextdetector.pt',
            'sha256_pre_calculated': '1f90fa60aeeb1eb82e2ac1167a66bf139a8a61b8780acd351ead55268540cccb'
        },
        {
            'url': 'https://huggingface.co/dreMaz/mit_models/resolve/main/comictextdetector.pt.onnx',
            'files': 'data/models/comictextdetector.pt.onnx',
            'sha256_pre_calculated': '1a86ace74961413cbd650002e7bb4dcec4980ffa21b2f19b86933372071d718f'
        }
    ]

    device = DEFAULT_DEVICE
    detect_size = 1024
    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.model: CTDModel = None

    @property
    def device(self):
        return self.params['device']['value']
    
    @property
    def detect_size(self):
        return int(self.params['detect_size']['value'])

    def _load_model(self):
        max_batches = int(self.get_param_value('det_rearrange_max_batches'))
        if self.device != 'cpu':
            self.model = load_ctd_model(
                CTD_TORCH_PATH,
                self.device,
                self.detect_size,
                max_batches,
            )
        else:
            self.model = load_ctd_model(
                CTD_ONNX_PATH,
                self.device,
                self.detect_size,
                max_batches,
            )

    def _detect(self, img: np.ndarray, proj: ProjImgTrans) -> Tuple[np.ndarray, List[TextBlock]]:
        _, mask, blk_list = self.model(img)
        
        fnt_rsz = self.get_param_value('font size multiplier')
        fnt_max = self.get_param_value('font size max')
        fnt_min = self.get_param_value('font size min')
        for blk in blk_list:
            sz = blk._detected_font_size * fnt_rsz
            if fnt_max > 0:
                sz = min(fnt_max, sz)
            if fnt_min > 0:
                sz = max(fnt_min, sz)
            blk.font_size = sz
            blk._detected_font_size = sz

        ksize = self.get_param_value('mask dilate size')
        if ksize > 0:
            element = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * ksize + 1, 2 * ksize + 1),(ksize, ksize))
            mask = cv2.dilate(mask, element)

        return mask, blk_list

    def updateParam(self, param_key: str, param_content):
        super().updateParam(param_key, param_content)
        if self.all_model_loaded():
            if param_key == 'device' and self.model.device != self.device:
                self.unload_model()
                self.load_model()
            elif param_key == 'detect_size':
                self.model.detect_size = self.detect_size
            elif param_key == 'det_rearrange_max_batches':
                self.model.det_rearrange_max_batches = int(
                    self.get_param_value(param_key)
                )
