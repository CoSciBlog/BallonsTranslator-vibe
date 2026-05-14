import os.path as osp
import sys
import unittest

import numpy as np

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.decensor import looks_like_binary_mask_image, select_decensor_input_image


class FakeProject:
    def __init__(self):
        self.current_img = "page.png"
        self.img_array = None
        self.original = None
        self.cleaned = None
        self.fallback = None

    def read_img(self, imgname):
        if self.original is None:
            raise FileNotFoundError(imgname)
        return self.original.copy()

    def load_inpainted_by_imgname(self, imgname):
        if self.cleaned is None:
            return None
        return self.cleaned.copy()

    def ensure_upscaled_img(self, imgname):
        if self.fallback is None:
            raise FileNotFoundError(imgname)
        return self.fallback.copy()


class DecensorSourceSelectionTest(unittest.TestCase):
    def test_original_image_is_preferred(self):
        project = FakeProject()
        project.original = np.full((20, 30, 3), 120, dtype=np.uint8)
        project.cleaned = np.full((20, 30, 3), 140, dtype=np.uint8)

        image, source = select_decensor_input_image(project, "page.png")

        self.assertEqual(source, "original")
        self.assertEqual(int(image[0, 0, 0]), 120)

    def test_current_image_is_used_when_original_is_missing(self):
        project = FakeProject()
        project.img_array = np.full((20, 30, 3), 130, dtype=np.uint8)
        project.cleaned = np.full((20, 30, 3), 140, dtype=np.uint8)

        image, source = select_decensor_input_image(project, "page.png")

        self.assertEqual(source, "current")
        self.assertEqual(int(image[0, 0, 0]), 130)

    def test_cleaned_image_is_used_when_original_and_current_are_missing(self):
        project = FakeProject()
        project.cleaned = np.full((20, 30, 3), 140, dtype=np.uint8)

        image, source = select_decensor_input_image(project, "page.png")

        self.assertEqual(source, "cleaned")
        self.assertEqual(int(image[0, 0, 0]), 140)

    def test_binary_mask_input_is_rejected(self):
        project = FakeProject()
        project.original = np.zeros((20, 30), dtype=np.uint8)
        project.original[5:15, 5:20] = 255

        with self.assertRaisesRegex(ValueError, "binary mask"):
            select_decensor_input_image(project, "page.png")

    def test_mask_or_debug_filename_is_not_automatically_selected(self):
        project = FakeProject()
        project.original = np.full((20, 30, 3), 120, dtype=np.uint8)

        with self.assertRaisesRegex(ValueError, "mask/debug"):
            select_decensor_input_image(project, "debug_mask.png")

    def test_binary_mask_detector(self):
        image = np.zeros((20, 30), dtype=np.uint8)
        image[5:15, 5:20] = 255

        self.assertTrue(looks_like_binary_mask_image(image))
        self.assertFalse(looks_like_binary_mask_image(np.full((20, 30, 3), 128, dtype=np.uint8)))


if __name__ == "__main__":
    unittest.main()
