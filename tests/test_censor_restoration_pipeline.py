import unittest
import os.path as osp
import sys
import tempfile

import numpy as np

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from modules.censor_restoration import CensorMaskDetector, CensorRestorationConfig, CensorRestorationPipeline
from modules.censor_restoration.detector import DetectionResult


class FakeInpainter:
    def __init__(self):
        self.received_mask = None
        self.received_textblock_list = "unset"

    def inpaint(self, img, mask, textblock_list=None, check_need_inpaint=False):
        self.received_mask = mask.copy()
        self.received_textblock_list = textblock_list
        result = img.copy()
        result[mask > 0] = 128
        return result


class FailingInpainter:
    def inpaint(self, img, mask, textblock_list=None, check_need_inpaint=False):
        raise RuntimeError("fake inpaint failure")


class EmptyDetector:
    def detect(self, image):
        return DetectionResult(mask=np.zeros(image.shape[:2], dtype=np.uint8), boxes=[], debug={})


class TextMaskDetector:
    def detect(self, image):
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        mask[20:40, 20:60] = 255
        return DetectionResult(mask=mask, boxes=[], debug={}, mask_role="text_inpaint")


class CensorRestorationPipelineTest(unittest.TestCase):
    def test_no_mask_found_returns_original_image(self):
        image = np.full((80, 80, 3), 128, dtype=np.uint8)
        pipeline = CensorRestorationPipeline(inpainter=FakeInpainter())

        result = pipeline.run(image)

        self.assertEqual(result.status, "no_censor_mask_found")
        self.assertEqual(result.boxes, [])
        self.assertTrue(np.array_equal(result.result_image, image))
        self.assertEqual(int(result.mask.sum()), 0)
        self.assertEqual(result.mask_role, "censor_restoration")
        self.assertEqual(result.error_message, "No censor mask found. The text inpaint mask will not be used automatically.")

    def test_detected_mask_is_passed_to_inpainter(self):
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        image[45:55, 20:80] = 0
        inpainter = FakeInpainter()
        pipeline = CensorRestorationPipeline(inpainter=inpainter)

        result = pipeline.run(image)

        self.assertEqual(result.status, "success")
        self.assertIsNone(inpainter.received_textblock_list)
        self.assertIsNotNone(inpainter.received_mask)
        self.assertGreater(int(inpainter.received_mask.sum()), 0)
        self.assertTrue(np.any(result.result_image[result.mask > 0] == 128))

    def test_inpainter_failure_returns_error_result(self):
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        image[45:55, 20:80] = 0
        pipeline = CensorRestorationPipeline(inpainter=FailingInpainter())

        result = pipeline.run(image)

        self.assertEqual(result.status, "error")
        self.assertIn("fake inpaint failure", result.error_message)
        self.assertTrue(np.array_equal(result.result_image, image))

    def test_invalid_image_returns_error_result(self):
        pipeline = CensorRestorationPipeline(inpainter=FakeInpainter())

        result = pipeline.run(object())

        self.assertEqual(result.status, "error")
        self.assertIsNone(result.original_image)
        self.assertIsNone(result.result_image)
        self.assertIn("TypeError", result.error_message)

    def test_text_inpaint_mask_is_not_used_when_detector_finds_no_censor_mask(self):
        image = np.full((80, 80, 3), 128, dtype=np.uint8)
        inpainter = FakeInpainter()
        pipeline = CensorRestorationPipeline(detector=EmptyDetector(), inpainter=inpainter)

        result = pipeline.run(image)

        self.assertEqual(result.status, "no_censor_mask_found")
        self.assertIsNone(inpainter.received_mask)

    def test_text_inpaint_detector_role_is_rejected(self):
        image = np.full((80, 80, 3), 128, dtype=np.uint8)
        inpainter = FakeInpainter()
        pipeline = CensorRestorationPipeline(detector=TextMaskDetector(), inpainter=inpainter)

        result = pipeline.run(image)

        self.assertEqual(result.status, "error")
        self.assertEqual(result.mask_role, "text_inpaint")
        self.assertIsNone(inpainter.received_mask)

    def test_run_with_manual_censor_mask_rejects_empty_mask(self):
        image = np.full((80, 80, 3), 128, dtype=np.uint8)
        mask = np.zeros((80, 80), dtype=np.uint8)
        pipeline = CensorRestorationPipeline(inpainter=FakeInpainter())

        result = pipeline.run_with_manual_censor_mask(image, mask)

        self.assertEqual(result.status, "no_censor_mask_found")
        self.assertEqual(int(result.mask.sum()), 0)
        self.assertEqual(result.mask_source, "manual")

    def test_run_with_manual_censor_mask_passes_non_empty_mask_to_inpainter(self):
        image = np.full((80, 80, 3), 128, dtype=np.uint8)
        mask = np.zeros((80, 80), dtype=np.float32)
        mask[20:30, 20:40] = 1.0
        inpainter = FakeInpainter()
        pipeline = CensorRestorationPipeline(inpainter=inpainter)

        result = pipeline.run_with_manual_censor_mask(image, mask)

        self.assertEqual(result.status, "success")
        self.assertIsNotNone(inpainter.received_mask)
        self.assertEqual(inpainter.received_mask.dtype, np.uint8)
        self.assertGreater(int(inpainter.received_mask.sum()), 0)
        self.assertEqual(result.mask_role, "censor_restoration")

    def test_run_with_manual_censor_mask_rejects_text_inpaint_role(self):
        image = np.full((80, 80, 3), 128, dtype=np.uint8)
        mask = np.zeros((80, 80), dtype=np.uint8)
        mask[20:30, 20:40] = 255
        inpainter = FakeInpainter()
        pipeline = CensorRestorationPipeline(inpainter=inpainter)

        result = pipeline.run_with_manual_censor_mask(image, mask, mask_role="text_inpaint")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.mask_role, "text_inpaint")
        self.assertIsNone(inpainter.received_mask)

    def test_run_with_manual_censor_mask_rejects_wrong_shape(self):
        image = np.full((80, 80, 3), 128, dtype=np.uint8)
        mask = np.ones((40, 40), dtype=np.uint8)
        pipeline = CensorRestorationPipeline(inpainter=FakeInpainter())

        result = pipeline.run_with_manual_censor_mask(image, mask)

        self.assertEqual(result.status, "error")
        self.assertIn("mask shape", result.error_message)

    def test_binary_mask_input_image_is_rejected(self):
        image = np.zeros((80, 80), dtype=np.uint8)
        image[20:60, 20:60] = 255
        pipeline = CensorRestorationPipeline(inpainter=FakeInpainter())

        result = pipeline.run(image)

        self.assertEqual(result.status, "error")
        self.assertIn("binary mask", result.error_message)

    def test_debug_json_is_written_when_enabled(self):
        image = np.full((80, 80, 3), 128, dtype=np.uint8)
        detector = CensorMaskDetector(CensorRestorationConfig(save_debug_masks=True))
        pipeline = CensorRestorationPipeline(detector=detector, inpainter=FakeInpainter())

        with tempfile.TemporaryDirectory() as tmpdir:
            result = pipeline.run(image, debug_output_dir=tmpdir)

            self.assertEqual(result.status, "no_censor_mask_found")
            self.assertIn("detection", result.debug_paths)
            self.assertTrue(osp.exists(result.debug_paths["detection"]))
            self.assertTrue(osp.exists(osp.join(tmpdir, "_final_mask.png")))


if __name__ == "__main__":
    unittest.main()
