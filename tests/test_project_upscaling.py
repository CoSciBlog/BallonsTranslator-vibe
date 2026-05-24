import os
import os.path as osp
import sys
import tempfile
import unittest

import cv2
import numpy as np

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.insert(0, APP_ROOT)

from utils.proj_imgtrans import ProjImgTrans
from utils.textblock import TextBlock
from utils.upscale import filename_has_upscale_marker, project_upscale_filename


class ProjectUpscalingTest(unittest.TestCase):
    def test_output_filename_uses_requested_factor_and_detects_marker(self):
        self.assertEqual(project_upscale_filename("001.png", 2), "001_upscaled_2x.png")
        self.assertEqual(project_upscale_filename("001.jpg", 2.5), "001_upscaled_2_5x.jpg")
        self.assertTrue(filename_has_upscale_marker("001_UPSCALED_2x.png"))
        self.assertFalse(filename_has_upscale_marker("001.png"))

    def test_replacing_project_page_renames_file_scales_geometry_and_resets_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            source_name = "001.png"
            target_name = "001_upscaled_2x.png"
            source_path = osp.join(directory, source_name)
            staged_path = osp.join(directory, "staged.png")
            cv2.imwrite(source_path, np.zeros((12, 10, 3), dtype=np.uint8))
            cv2.imwrite(staged_path, np.zeros((24, 20, 3), dtype=np.uint8))

            project = ProjImgTrans(directory)
            os.makedirs(project.inpainted_dir())
            matching_generated = osp.join(project.inpainted_dir(), "001.png")
            unrelated_generated = osp.join(project.inpainted_dir(), "002.png")
            cv2.imwrite(matching_generated, np.zeros((12, 10, 3), dtype=np.uint8))
            cv2.imwrite(unrelated_generated, np.zeros((12, 10, 3), dtype=np.uint8))
            block = TextBlock(xyxy=[1, 2, 5, 6], lines=[[[1, 2], [5, 2], [5, 6], [1, 6]]])
            project.pages[source_name] = [block]
            project._image_info[source_name]["finish_code"] = 31

            project.replace_pages_with_upscaled_files([{
                "source_name": source_name,
                "target_name": target_name,
                "staged_path": staged_path,
                "used_factor": 2.0,
                "width": 20,
                "height": 24,
                "original_width": 10,
                "original_height": 12,
            }])

            self.assertFalse(osp.exists(source_path))
            self.assertTrue(osp.exists(osp.join(directory, target_name)))
            self.assertIn(target_name, project.pages)
            self.assertEqual(project.pages[target_name][0].xyxy, [2, 4, 10, 12])
            self.assertEqual(project._image_info[target_name]["finish_code"], 0)
            self.assertEqual(project.current_img, target_name)
            self.assertFalse(osp.exists(matching_generated))
            self.assertTrue(osp.exists(unrelated_generated))


if __name__ == "__main__":
    unittest.main()
