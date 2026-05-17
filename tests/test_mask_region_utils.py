import os.path as osp
import sys
import unittest

import numpy as np

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.imgproc_utils import get_connected_block_mask


class MaskRegionUtilsTest(unittest.TestCase):
    def test_connected_block_mask_expands_to_full_component(self):
        mask = np.zeros((80, 120), dtype=np.uint8)
        mask[30:35, 10:110] = 255
        mask[10:20, 80:90] = 255

        component, rect = get_connected_block_mask([45, 25, 12, 20], mask, 0)

        self.assertEqual(rect, [10, 30, 110, 35])
        self.assertEqual(int(component.sum()), 100 * 5 * 255)

    def test_connected_block_mask_ignores_unrelated_components(self):
        mask = np.zeros((80, 120), dtype=np.uint8)
        mask[30:35, 10:110] = 255
        mask[10:20, 80:90] = 255

        component, rect = get_connected_block_mask([82, 12, 4, 4], mask, 0)

        self.assertEqual(rect, [80, 10, 90, 20])
        self.assertEqual(int(component.sum()), 10 * 10 * 255)

    def test_connected_block_mask_returns_none_without_overlap(self):
        mask = np.zeros((80, 120), dtype=np.uint8)
        mask[30:35, 10:110] = 255

        component, rect = get_connected_block_mask([20, 10, 10, 10], mask, 0)

        self.assertIsNone(component)
        self.assertIsNone(rect)


if __name__ == "__main__":
    unittest.main()
