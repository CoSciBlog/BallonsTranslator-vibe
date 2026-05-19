import base64
import json
import os
import os.path as osp
import sys
import tempfile
import unittest
import zipfile

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.archive_import import archive_project_dir, import_archive_to_project, is_archive_path
from utils.io_utils import find_all_imgs


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYPgPAAEDAQB2"
    "p6YAAAAASUVORK5CYII="
)


class ArchiveImportTest(unittest.TestCase):
    def _write_archive(self, path, members):
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)

    def test_zip_archive_imports_images_as_project_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = osp.join(tmpdir, "Comic.zip")
            self._write_archive(
                archive_path,
                {
                    "chapter/page10.png": PNG_1X1,
                    "chapter/page2.png": PNG_1X1,
                    "notes.txt": b"ignore me",
                },
            )

            project_dir = import_archive_to_project(archive_path)

            self.assertEqual(project_dir, osp.join(tmpdir, "Comic"))
            self.assertEqual(find_all_imgs(project_dir, sort=True), ["0001_page2.png", "0002_page10.png"])
            with open(osp.join(project_dir, "archive_import.json"), "r", encoding="utf8") as f:
                metadata = json.load(f)
            self.assertEqual(metadata["image_count"], 2)
            self.assertEqual(metadata["images"], ["0001_page2.png", "0002_page10.png"])

    def test_cbz_archive_uses_zip_import_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = osp.join(tmpdir, "Manga.cbz")
            self._write_archive(archive_path, {"001.jpg": PNG_1X1})

            project_dir = import_archive_to_project(archive_path)

            self.assertEqual(find_all_imgs(project_dir, sort=True), ["0001_001.jpg"])

    def test_existing_import_folder_is_reused_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = osp.join(tmpdir, "Book.zip")
            project_dir = archive_project_dir(archive_path)
            os.makedirs(project_dir)
            with open(osp.join(project_dir, "0001_existing.png"), "wb") as f:
                f.write(PNG_1X1)
            self._write_archive(archive_path, {"new.png": PNG_1X1})

            self.assertEqual(import_archive_to_project(archive_path), project_dir)
            self.assertEqual(find_all_imgs(project_dir, sort=True), ["0001_existing.png"])

    def test_archive_extension_detection(self):
        self.assertTrue(is_archive_path("comic.cbz"))
        self.assertTrue(is_archive_path("comic.CBR"))
        self.assertTrue(is_archive_path("comic.zip"))
        self.assertFalse(is_archive_path("comic.png"))


if __name__ == "__main__":
    unittest.main()
