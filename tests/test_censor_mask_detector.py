import unittest
import os.path as osp
import sys

import numpy as np

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from modules.censor_restoration import CensorMaskDetector, CensorRestorationConfig


class CensorMaskDetectorTest(unittest.TestCase):
    def detector(self, **overrides):
        config = CensorRestorationConfig(**overrides)
        return CensorMaskDetector(config)

    def test_detects_dark_horizontal_bar(self):
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        image[45:55, 20:80] = 0

        result = self.detector().detect(image)

        self.assertEqual(len(result.boxes), 1)
        self.assertEqual(result.boxes[0].kind, "dark")
        self.assertGreater(result.mask.sum(), 0)
        self.assertEqual(result.mask.dtype, np.uint8)

    def test_detects_light_horizontal_bar(self):
        image = np.full((100, 100, 3), 128, dtype=np.uint8)
        image[45:55, 20:80] = 255

        result = self.detector().detect(image)

        self.assertEqual(len(result.boxes), 1)
        self.assertEqual(result.boxes[0].kind, "light")
        self.assertGreater(result.mask.sum(), 0)

    def test_empty_image_has_no_mask(self):
        image = np.full((100, 100, 3), 128, dtype=np.uint8)

        result = self.detector().detect(image)

        self.assertEqual(result.boxes, [])
        self.assertEqual(int(result.mask.sum()), 0)
        self.assertIn("dark_contours", result.debug)
        self.assertIn("light_contours", result.debug)
        self.assertEqual(result.debug["final_box_count"], 0)
        self.assertEqual(result.debug["mask_pixel_count"], 0)

    def test_small_dark_artifacts_are_ignored(self):
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        image[10:12, 10:12] = 0
        image[50:52, 60:62] = 0

        result = self.detector().detect(image)

        self.assertEqual(result.boxes, [])
        self.assertEqual(int(result.mask.sum()), 0)

    def test_padding_expands_detected_mask(self):
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        image[45:55, 20:80] = 0

        result = self.detector(mask_padding=8).detect(image)

        self.assertEqual(len(result.boxes), 1)
        box = result.boxes[0]
        self.assertLessEqual(box.x, 12)
        self.assertLessEqual(box.y, 37)
        self.assertGreaterEqual(box.width, 76)
        self.assertGreaterEqual(box.height, 26)
        self.assertEqual(result.mask[37, 12], 255)

    def test_detects_dark_blocky_region(self):
        image = np.full((120, 120, 3), 180, dtype=np.uint8)
        image[45:70, 45:70] = 10

        result = self.detector().detect(image)

        self.assertGreaterEqual(len(result.boxes), 1)
        self.assertGreater(int(result.mask.sum()), 0)

    def test_merges_nearby_bars(self):
        image = np.full((120, 120, 3), 255, dtype=np.uint8)
        image[45:52, 20:60] = 0
        image[45:52, 66:100] = 0

        result = self.detector(merge_distance=12).detect(image)

        self.assertEqual(len(result.boxes), 1)
        self.assertLessEqual(result.boxes[0].x, 20)
        self.assertGreaterEqual(result.boxes[0].x + result.boxes[0].width, 100)

    def test_very_thin_panel_line_is_ignored(self):
        image = np.full((120, 120, 3), 255, dtype=np.uint8)
        image[20:21, 5:115] = 0

        result = self.detector(morph_kernel_size=1).detect(image)

        self.assertEqual(result.boxes, [])
        self.assertEqual(int(result.mask.sum()), 0)

    def test_large_page_border_is_ignored(self):
        image = np.full((120, 120, 3), 255, dtype=np.uint8)
        image[0:8, :] = 0

        result = self.detector().detect(image)

        self.assertEqual(result.boxes, [])
        self.assertEqual(int(result.mask.sum()), 0)


if __name__ == "__main__":
    unittest.main()
