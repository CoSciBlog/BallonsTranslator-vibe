import os
import os.path as osp
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, osp.dirname(osp.dirname(__file__)))

from utils.batch_processing import collect_batch_project_dirs, parse_batch_paths


class BatchProcessingTest(unittest.TestCase):
    def _write_image(self, path):
        Image.new("RGB", (8, 8), (255, 255, 255)).save(path)

    def test_collects_immediate_image_subfolders_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chapter_a = osp.join(tmpdir, "Chapter 01")
            chapter_b = osp.join(tmpdir, "Chapter 02")
            nested_parent = osp.join(tmpdir, "Nested")
            nested_child = osp.join(nested_parent, "Child")
            for path in [chapter_a, chapter_b, nested_child]:
                os.makedirs(path)
            self._write_image(osp.join(chapter_a, "001.png"))
            self._write_image(osp.join(chapter_b, "001.jpg"))
            self._write_image(osp.join(nested_child, "001.png"))

            self.assertEqual(
                collect_batch_project_dirs(tmpdir),
                [chapter_a, chapter_b],
            )

    def test_ignores_generated_project_folders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["mask", "result", "inpainted", "upscaled"]:
                path = osp.join(tmpdir, name)
                os.makedirs(path)
                self._write_image(osp.join(path, "001.png"))
            chapter = osp.join(tmpdir, "Chapter")
            os.makedirs(chapter)
            self._write_image(osp.join(chapter, "001.png"))

            self.assertEqual(collect_batch_project_dirs(tmpdir), [chapter])

    def test_accepts_direct_project_and_multiple_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_a = osp.join(tmpdir, "Chapter A")
            project_b = osp.join(tmpdir, "Chapter B")
            os.makedirs(project_a)
            os.makedirs(project_b)
            self._write_image(osp.join(project_a, "001.png"))
            self._write_image(osp.join(project_b, "001.png"))

            entered = f'{project_a};\n"{project_b}";{project_a}'
            self.assertEqual(parse_batch_paths(entered), [project_a, project_b])
            self.assertEqual(collect_batch_project_dirs(entered), [project_a, project_b])


if __name__ == "__main__":
    unittest.main()
