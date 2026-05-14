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
        self.assertEqual(result.mask_role, "censor_restoration")

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

    def test_detects_gray_rectangular_region(self):
        image = np.full((120, 120, 3), 255, dtype=np.uint8)
        image[45:65, 35:65] = 150

        result = self.detector().detect(image)

        self.assertGreaterEqual(len(result.boxes), 1)
        self.assertIn("gray", {box.kind for box in result.boxes})
        self.assertGreater(int(result.mask.sum()), 0)
        self.assertIn("gray_candidates", result.debug)

    def test_detects_gray_horizontal_banded_region(self):
        image = np.full((120, 120, 3), 255, dtype=np.uint8)
        image[45:65, 35:75] = 150
        image[46:65:4, 35:75] = 110

        result = self.detector().detect(image)

        self.assertGreaterEqual(len(result.boxes), 1)
        self.assertGreater(result.debug["banded_candidates"], 0)
        self.assertGreater(int(result.mask.sum()), 0)

    def test_detects_two_small_gray_censor_blocks(self):
        image = np.full((140, 140, 3), 255, dtype=np.uint8)
        image[40:58, 35:55] = 145
        image[82:102, 80:104] = 155

        result = self.detector().detect(image)

        self.assertGreaterEqual(len(result.boxes), 2)
        self.assertGreater(int(result.mask.sum()), 0)

    def test_large_white_speech_bubble_is_not_detected(self):
        image = np.full((140, 140, 3), 150, dtype=np.uint8)
        yy, xx = np.ogrid[:140, :140]
        bubble = ((xx - 70) ** 2 / (48 ** 2) + (yy - 70) ** 2 / (34 ** 2)) <= 1
        image[bubble] = 255

        result = self.detector().detect(image)

        self.assertEqual(result.boxes, [])
        self.assertEqual(int(result.mask.sum()), 0)

    def test_black_text_glyphs_are_not_detected(self):
        image = np.full((120, 120, 3), 255, dtype=np.uint8)
        image[35:70, 30:34] = 0
        image[35:39, 30:48] = 0
        image[52:56, 30:44] = 0
        image[35:70, 55:59] = 0
        image[66:70, 55:75] = 0

        result = self.detector().detect(image)

        self.assertEqual(result.boxes, [])
        self.assertEqual(int(result.mask.sum()), 0)

    def test_large_white_text_inpaint_mask_is_not_detected(self):
        image = np.full((120, 120, 3), 160, dtype=np.uint8)
        image[30:90, 35:85] = 255

        result = self.detector().detect(image)

        self.assertEqual(result.boxes, [])
        self.assertEqual(int(result.mask.sum()), 0)

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
