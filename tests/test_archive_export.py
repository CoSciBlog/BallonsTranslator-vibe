import os.path as osp
import re
import sys
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.archive_export import ArchiveExportError, export_images, is_export_path


class ArchiveExportTest(unittest.TestCase):
    def _write_image(self, path, size, color):
        Image.new("RGB", size, color).save(path)

    def test_zip_and_cbz_export_include_pages_in_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first = osp.join(tmpdir, "page10.png")
            second = osp.join(tmpdir, "page2.jpg")
            self._write_image(first, (4, 6), "red")
            self._write_image(second, (3, 5), "blue")

            output = osp.join(tmpdir, "Book.cbz")
            export_images([("page10.png", first), ("page2.jpg", second)], output)

            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["0001_page10.png", "0002_page2.jpg"],
                )

    def test_pdf_export_uses_each_image_size_as_own_page_size(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            portrait = osp.join(tmpdir, "portrait.png")
            landscape = osp.join(tmpdir, "landscape.png")
            self._write_image(portrait, (40, 80), "white")
            self._write_image(landscape, (120, 50), "black")

            output = osp.join(tmpdir, "Book.pdf")
            export_images([("portrait.png", portrait), ("landscape.png", landscape)], output)

            with open(output, "rb") as f:
                pdf = f.read().decode("latin1")
            boxes = re.findall(r"/MediaBox \[ 0 0 ([0-9.]+) ([0-9.]+) \]", pdf)
            self.assertIn(("40.0", "80.0"), boxes)
            self.assertIn(("120.0", "50.0"), boxes)

    def test_cbr_export_invokes_rar_writer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image = osp.join(tmpdir, "page.png")
            self._write_image(image, (4, 4), "green")
            output = osp.join(tmpdir, "Book.cbr")

            def fake_run(command, **kwargs):
                with open(command[4], "wb") as f:
                    f.write(b"rar")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with patch("utils.archive_export._rar_command", return_value="rar"), \
                    patch("utils.archive_export.subprocess.run", side_effect=fake_run) as run_mock:
                export_images([("page.png", image)], output)

            self.assertTrue(osp.exists(output))
            self.assertEqual(run_mock.call_args[0][0][0], "rar")

    def test_cbr_export_reports_missing_rar_writer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image = osp.join(tmpdir, "page.png")
            self._write_image(image, (4, 4), "green")

            with patch("utils.archive_export._rar_command", side_effect=ArchiveExportError("missing rar")):
                with self.assertRaises(ArchiveExportError):
                    export_images([("page.png", image)], osp.join(tmpdir, "Book.cbr"))

    def test_export_extension_detection(self):
        self.assertTrue(is_export_path("comic.cbz"))
        self.assertTrue(is_export_path("comic.CBR"))
        self.assertTrue(is_export_path("comic.zip"))
        self.assertTrue(is_export_path("comic.pdf"))
        self.assertFalse(is_export_path("comic.png"))


if __name__ == "__main__":
    unittest.main()
