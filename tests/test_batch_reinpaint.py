import os.path as osp
import sys
import unittest

import numpy as np

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.reinpaint import reinpaint_project_page


class BatchReinpaintTest(unittest.TestCase):
    def test_reinpaint_project_page_combines_saved_masks_and_saves_result(self):
        source_img = np.zeros((6, 6, 3), dtype=np.uint8)
        text_mask = np.zeros((6, 6), dtype=np.uint8)
        text_mask[1:3, 1:3] = 255
        decensor_mask = np.zeros((6, 6), dtype=np.uint8)
        decensor_mask[4:5, 4:5] = 255
        result_img = np.full((6, 6, 3), 127, dtype=np.uint8)

        class DummyProject:
            pages = {"page.png": []}
            current_img = "page.png"
            inpainted_array = None

            def load_inpainted_by_imgname(self, page_name):
                self.loaded_page = page_name
                return source_img

            def ensure_upscaled_img(self, page_name):
                raise AssertionError("existing inpainted result should be preferred")

            def load_mask_by_imgname(self, page_name):
                return text_mask

            def load_decensor_mask_by_imgname(self, page_name):
                return decensor_mask

            def save_inpainted(self, page_name, image):
                self.saved_page = page_name
                self.saved_image = image

        class DummyInpainter:
            def inpaint(self, image, mask, blocks):
                self.image = image
                self.mask = mask
                self.blocks = blocks
                return result_img

        project = DummyProject()
        inpainter = DummyInpainter()

        self.assertTrue(reinpaint_project_page(project, inpainter, "page.png"))
        self.assertGreater(np.count_nonzero(inpainter.mask[1:3, 1:3]), 0)
        self.assertGreater(np.count_nonzero(inpainter.mask[4:5, 4:5]), 0)
        self.assertEqual(project.saved_page, "page.png")
        np.testing.assert_array_equal(project.saved_image, result_img)
        np.testing.assert_array_equal(project.inpainted_array, result_img)


if __name__ == "__main__":
    unittest.main()
