import unittest
import os.path as osp
import sys

import numpy as np

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.reinpaint import combine_inpaint_masks, mask_bounding_rect, normalize_inpaint_mask


class ReinpaintMaskTests(unittest.TestCase):
    def test_no_mask_returns_none(self):
        self.assertIsNone(combine_inpaint_masks([None], (8, 8)))

    def test_one_mask_is_binarized(self):
        mask = np.zeros((4, 4), dtype=np.uint8)
        mask[1, 2] = 17
        combined = combine_inpaint_masks([mask], (4, 4))
        self.assertEqual(combined[1, 2], 255)
        self.assertEqual(int(combined.sum()), 255)

    def test_multiple_masks_are_combined(self):
        first = np.zeros((5, 5), dtype=np.uint8)
        second = np.zeros((5, 5), dtype=np.uint8)
        first[1, 1] = 255
        second[3, 3] = 255
        combined = combine_inpaint_masks([first, second], (5, 5))
        self.assertEqual(combined[1, 1], 255)
        self.assertEqual(combined[3, 3], 255)
        self.assertEqual(np.count_nonzero(combined), 2)

    def test_mask_is_resized_with_nearest_neighbor(self):
        mask = np.zeros((2, 2), dtype=np.uint8)
        mask[0, 0] = 255
        normalized = normalize_inpaint_mask(mask, (4, 4))
        self.assertEqual(normalized.shape, (4, 4))
        self.assertEqual(normalized[0, 0], 255)
        self.assertEqual(normalized[3, 3], 0)

    def test_dilate_expands_mask(self):
        mask = np.zeros((7, 7), dtype=np.uint8)
        mask[3, 3] = 255
        combined = combine_inpaint_masks([mask], (7, 7), dilate=1)
        self.assertGreater(np.count_nonzero(combined), 1)
        self.assertEqual(combined[3, 3], 255)

    def test_bounding_rect_uses_nonzero_pixels(self):
        mask = np.zeros((10, 10), dtype=np.uint8)
        mask[2:5, 4:7] = 255
        self.assertEqual(mask_bounding_rect(mask), (4, 2, 7, 5))


if __name__ == '__main__':
    unittest.main()
