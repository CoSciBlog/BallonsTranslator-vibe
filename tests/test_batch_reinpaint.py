import os.path as osp
import sys
import unittest
from pathlib import Path

import numpy as np

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.reinpaint import reinpaint_project_page


class BatchReinpaintTest(unittest.TestCase):
    def test_all_pages_reinpaint_menu_is_connected_to_complete_project(self):
        root = Path(APP_ROOT)
        bars_source = (root / "ui" / "mainwindowbars.py").read_text(encoding="utf-8")
        mainwindow_source = (root / "ui" / "mainwindow.py").read_text(encoding="utf-8")

        self.assertIn("QAction(self.tr('Re-run Inpainting All Pages')", bars_source)
        self.assertIn(
            "self.titleBar.reinpaint_all_pages_trigger.connect(self.run_reinpaint_all_pages)",
            mainwindow_source,
        )
        self.assertIn("page_names = list(self.imgtrans_proj.pages.keys())", mainwindow_source)
        self.assertIn("self.module_manager.runReinpaintPipeline(page_names)", mainwindow_source)

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

    def test_all_pages_reinpaint_can_start_from_original_source(self):
        original_img = np.full((4, 4, 3), 25, dtype=np.uint8)
        inpainted_img = np.full((4, 4, 3), 90, dtype=np.uint8)
        mask = np.full((4, 4), 255, dtype=np.uint8)

        class DummyProject:
            pages = {"page.png": []}
            current_img = None

            def load_inpainted_by_imgname(self, page_name):
                return inpainted_img

            def ensure_upscaled_img(self, page_name):
                return original_img

            def load_mask_by_imgname(self, page_name):
                return mask

            def load_decensor_mask_by_imgname(self, page_name):
                return None

            def save_inpainted(self, page_name, image):
                self.saved_image = image

        class DummyInpainter:
            def inpaint(self, image, inpaint_mask, blocks):
                self.source_image = image
                return image

        project = DummyProject()
        inpainter = DummyInpainter()

        self.assertTrue(
            reinpaint_project_page(
                project,
                inpainter,
                "page.png",
                use_original_source=True,
            )
        )
        np.testing.assert_array_equal(inpainter.source_image, original_img)


if __name__ == "__main__":
    unittest.main()
