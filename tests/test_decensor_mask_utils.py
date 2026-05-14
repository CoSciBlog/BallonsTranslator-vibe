import os.path as osp
import sys
import unittest

import numpy as np

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.decensor import build_decensor_mask


class DecensorMaskUtilsTest(unittest.TestCase):
    def test_build_decensor_mask_returns_debug_data(self):
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        image[45:55, 20:80] = 0

        mask, mode, debug = build_decensor_mask(image, mode="bars", return_debug=True)

        self.assertEqual(mode, "bars")
        self.assertGreater(int(mask.sum()), 0)
        self.assertIn("thresholds", debug)
        self.assertIn("mask_pixel_count", debug)

    def test_build_decensor_mask_detects_blocky_region(self):
        image = np.full((120, 120, 3), 180, dtype=np.uint8)
        image[45:70, 45:70] = 0

        mask, _, _ = build_decensor_mask(image, mode="bars", return_debug=True)

        self.assertGreater(int(mask.sum()), 0)

    def test_build_decensor_mask_no_candidate(self):
        image = np.full((100, 100, 3), 128, dtype=np.uint8)

        mask, _, debug = build_decensor_mask(image, mode="bars", return_debug=True)

        self.assertEqual(int(mask.sum()), 0)
        self.assertEqual(debug["mask_pixel_count"], 0)


if __name__ == "__main__":
    unittest.main()
