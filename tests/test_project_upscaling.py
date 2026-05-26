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
from utils.upscale import filename_has_upscale_marker, project_upscale_filename, reduce_compression_artifacts
from utils.batch_processing import collect_batch_project_dirs
from ui.io_thread import BatchProjectUpscaleThread


class ProjectUpscalingTest(unittest.TestCase):
    def test_output_filename_uses_requested_factor_and_detects_marker(self):
        self.assertEqual(project_upscale_filename("001.png", 2), "001_upscaled_2x.png")
        self.assertEqual(project_upscale_filename("001.jpg", 2.5), "001_upscaled_2_5x.jpg")
        self.assertTrue(filename_has_upscale_marker("001_UPSCALED_2x.png"))
        self.assertFalse(filename_has_upscale_marker("001.png"))

    def test_compression_cleanup_is_optional_and_processes_enabled_images(self):
        image = np.zeros((20, 20, 3), dtype=np.uint8)
        image[::2, ::2] = 255

        self.assertIs(reduce_compression_artifacts(image, "off"), image)
        cleaned = reduce_compression_artifacts(image, "medium")

        self.assertEqual(cleaned.shape, image.shape)
        self.assertFalse(np.array_equal(cleaned, image))

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

    def test_batch_upscaling_processes_source_folders_and_leaves_generated_folders_untouched(self):
        with tempfile.TemporaryDirectory() as root_dir:
            source_dir = osp.join(root_dir, "Chapter 01")
            generated_dir = osp.join(root_dir, "result")
            os.makedirs(source_dir)
            os.makedirs(generated_dir)
            cv2.imwrite(osp.join(source_dir, "001.png"), np.zeros((12, 10, 3), dtype=np.uint8))
            cv2.imwrite(osp.join(generated_dir, "001.png"), np.zeros((12, 10, 3), dtype=np.uint8))

            jobs = [(directory, ["001.png"]) for directory in collect_batch_project_dirs(root_dir)]
            self.assertEqual(jobs, [(source_dir, ["001.png"])])

            thread = BatchProjectUpscaleThread()
            completed = []
            thread.upscale_finished.connect(lambda *args: completed.append(args))
            thread.jobs = jobs
            thread.factor = 2.0
            thread.max_long_edge = 0
            thread.skip_above = 0
            thread.quality = "balanced"
            thread._run_upscale()

            self.assertTrue(completed)
            self.assertEqual(completed[0][0], 1)
            self.assertFalse(osp.exists(osp.join(source_dir, "001.png")))
            self.assertTrue(osp.exists(osp.join(source_dir, "001_upscaled_2x.png")))
            self.assertTrue(osp.exists(osp.join(generated_dir, "001.png")))
            self.assertFalse(osp.exists(osp.join(generated_dir, "001_upscaled_2x.png")))


if __name__ == "__main__":
    unittest.main()
