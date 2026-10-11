import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from ballontranslator.modules.lazy_registry import iter_lazy_module_specs
from ballontranslator.modules.inpaint.inpaint_default import (
    AOTInpainter,
    Flux2Klein,
    LamaLarge,
    LamaInpainterMPE,
    OpenCVInpainter,
    PatchmatchInpainter,
)
from ballontranslator.modules.ocr.ocr_manga import MangaOCR
from ballontranslator.modules.ocr.ocr_paddleVL_manga import PaddleOCRVLManga
from ballontranslator.modules.ocr.ocr_ppv6_onnx import PaddleOCRv6ONNX


class OCRAndInpaintSettingsTest(unittest.TestCase):
    def test_all_visible_ocr_and_inpaint_params_have_help(self) -> None:
        specs = [
            spec
            for spec in iter_lazy_module_specs(
                include_inactive_platform_branches=True
            )
            if spec.module_type in {'ocr', 'inpainter'}
        ]

        for spec in specs:
            for key, param in (spec.params or {}).items():
                if key == 'description' or key.startswith('__'):
                    continue
                with self.subTest(module=spec.key, parameter=key):
                    self.assertIsInstance(param, dict)
                    self.assertTrue(param.get('display_name'))
                    self.assertTrue(param.get('description'))

    def test_manga_ocr_exposes_generation_quality_controls(self) -> None:
        self.assertEqual(
            MangaOCR.params['max_new_tokens']['options'],
            [64, 128, 192, 256, 300],
        )
        self.assertEqual(MangaOCR.params['num_beams']['options'], [1, 2, 4, 6])

    def test_manga_ocr_forwards_and_updates_generation_settings(self) -> None:
        params = copy.deepcopy(MangaOCR.params)
        params['max_new_tokens']['value'] = 192
        params['num_beams']['value'] = 4
        detector = MangaOCR(**params)

        with patch(
            'ballontranslator.modules.ocr.ocr_manga.MangaOcr'
        ) as model_class:
            detector._load_model()
        model_class.assert_called_once_with(
            device=detector.device,
            max_new_tokens=192,
            num_beams=4,
        )

        detector.model = SimpleNamespace(
            max_new_tokens=192,
            num_beams=4,
            to=Mock(),
        )
        detector.updateParam('max_new_tokens', '256')
        detector.updateParam('num_beams', '2')
        self.assertEqual(detector.model.max_new_tokens, 256)
        self.assertEqual(detector.model.num_beams, 2)

    def test_vision_ocr_and_ppocr_expose_size_and_confidence(self) -> None:
        self.assertEqual(
            PaddleOCRVLManga.params['max_input_size']['options'],
            [512, 768, 1024, 1280, 1536],
        )
        self.assertEqual(
            PaddleOCRv6ONNX.params['confidence_threshold']['value'],
            0.3,
        )

    def test_opencv_inpainter_uses_selected_method_and_radius(self) -> None:
        params = copy.deepcopy(OpenCVInpainter.params)
        params['method']['value'] = 'Telea'
        params['radius']['value'] = 7
        inpainter = OpenCVInpainter(**params)
        image = np.zeros((4, 4, 3), dtype=np.uint8)
        mask = np.zeros((4, 4), dtype=np.uint8)

        with patch(
            'ballontranslator.modules.inpaint.inpaint_default.cv2.inpaint',
            return_value=image,
        ) as inpaint:
            result = inpainter._inpaint(image, mask)

        self.assertIs(result, image)
        self.assertEqual(inpaint.call_args.args[2], 7)
        self.assertEqual(inpaint.call_args.args[3], 1)  # cv2.INPAINT_TELEA

    def test_patchmatch_inpainter_uses_selected_patch_size(self) -> None:
        inpainter = PatchmatchInpainter.__new__(PatchmatchInpainter)
        inpainter.params = copy.deepcopy(PatchmatchInpainter.params)
        inpainter.params['patch_size']['value'] = 11
        inpainter.inpaint_method = Mock(return_value='result')

        result = inpainter._inpaint(Mock(), Mock())

        self.assertEqual(result, 'result')
        self.assertEqual(inpainter.inpaint_method.call_args.kwargs['patch_size'], 11)

    def test_local_inpainters_offer_extended_quality_ranges(self) -> None:
        for cls in (AOTInpainter, LamaInpainterMPE, LamaLarge):
            with self.subTest(inpainter=cls.__name__):
                sizes = cls.params['inpaint_size']['options']
                self.assertIn(1280, sizes)
                self.assertIn(2304, sizes)
                self.assertIn(2560, sizes)
        self.assertEqual(
            Flux2Klein.params['step']['options'],
            [4, 6, 8, 12, 16, 20],
        )


if __name__ == '__main__':
    unittest.main()
