import unittest
import os.path as osp
import sys

import numpy as np

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from modules.censor_restoration import CensorRestorationPipeline


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


class CensorRestorationPipelineTest(unittest.TestCase):
    def test_no_mask_found_returns_original_image(self):
        image = np.full((80, 80, 3), 128, dtype=np.uint8)
        pipeline = CensorRestorationPipeline(inpainter=FakeInpainter())

        result = pipeline.run(image)

        self.assertEqual(result.status, "no_mask_found")
        self.assertEqual(result.boxes, [])
        self.assertTrue(np.array_equal(result.result_image, image))
        self.assertEqual(int(result.mask.sum()), 0)

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


if __name__ == "__main__":
    unittest.main()
