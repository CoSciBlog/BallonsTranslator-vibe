import json
import os
import os.path as osp
import sys
import tempfile
import unittest
from unittest.mock import patch

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.proj_imgtrans import ProjImgTrans, safe_replace_with_retries
from ballontranslator.utils.textblock import TextBlock as PackageTextBlock


class ProjectSaveAtomicTest(unittest.TestCase):
    def test_safe_replace_normal_case(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = osp.join(tmpdir, "imgtrans_test.json")
            tmp = target + ".tmp"
            with open(target, "w", encoding="utf8") as f:
                json.dump({"old": True}, f)
            with open(tmp, "w", encoding="utf8") as f:
                json.dump({"new": True}, f)

            safe_replace_with_retries(tmp, target)

            self.assertFalse(osp.exists(tmp))
            with open(target, "r", encoding="utf8") as f:
                self.assertEqual(json.load(f), {"new": True})

    def test_safe_replace_retries_after_permission_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = osp.join(tmpdir, "imgtrans_test.json")
            tmp = target + ".tmp"
            with open(target, "w", encoding="utf8") as f:
                f.write("{}")
            with open(tmp, "w", encoding="utf8") as f:
                f.write('{"ok": true}')

            real_replace = os.replace
            calls = {"count": 0}

            def flaky_replace(src, dst):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise PermissionError(5, "Access is denied", dst)
                return real_replace(src, dst)

            with patch("utils.proj_imgtrans.os.replace", side_effect=flaky_replace):
                safe_replace_with_retries(tmp, target, retries=2, delay=0)

            self.assertEqual(calls["count"], 2)
            self.assertFalse(osp.exists(tmp))
            with open(target, "r", encoding="utf8") as f:
                self.assertEqual(json.load(f), {"ok": True})

    def test_safe_replace_keeps_tmp_after_repeated_permission_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = osp.join(tmpdir, "imgtrans_test.json")
            tmp = target + ".tmp"
            with open(target, "w", encoding="utf8") as f:
                f.write('{"old": true}')
            with open(tmp, "w", encoding="utf8") as f:
                f.write('{"new": true}')

            with patch(
                "utils.proj_imgtrans.os.replace",
                side_effect=PermissionError(5, "Access is denied", target),
            ):
                with self.assertRaises(PermissionError):
                    safe_replace_with_retries(tmp, target, retries=2, delay=0)

            self.assertTrue(osp.exists(tmp))
            with open(target, "r", encoding="utf8") as f:
                self.assertEqual(json.load(f), {"old": True})
            with open(tmp, "r", encoding="utf8") as f:
                self.assertEqual(json.load(f), {"new": True})

    def test_project_save_writes_glossary_to_separate_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = ProjImgTrans()
            proj.directory = tmpdir
            proj.proj_path = osp.join(tmpdir, "imgtrans_test.json")
            proj.pages = {}
            proj.not_found_pages = {}
            proj._image_info = {}
            proj.current_img = None
            proj.glossary = {
                "entries": "source => Cynthia [character]",
                "prompt": "Use project terms only.",
                "preferred_targets": "Cynthia [character]",
            }

            proj.save()

            with open(proj.proj_path, "r", encoding="utf8") as f:
                project_json = json.load(f)
            with open(osp.join(tmpdir, "glossary.json"), "r", encoding="utf8") as f:
                glossary_json = json.load(f)

            self.assertNotIn("glossary", project_json)
            self.assertEqual(glossary_json["entries"], "source => Cynthia [character]")
            self.assertEqual(glossary_json["prompt"], "Use project terms only.")
            self.assertEqual(glossary_json["preferred_targets"], "Cynthia [character]")

    def test_project_save_serializes_textblock_imported_through_package_alias(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj = ProjImgTrans()
            proj.directory = tmpdir
            proj.proj_path = osp.join(tmpdir, "imgtrans_test.json")
            blk = PackageTextBlock([0, 0, 10, 10], text=["source"])
            blk.region_inpaint_dict = {
                "inpaint_rect": [0, 0, 10, 10],
                "source_block": PackageTextBlock([1, 1, 2, 2], text=["nested"]),
            }
            proj.pages = {"page.png": [blk]}
            proj.not_found_pages = {}
            proj._image_info = {}
            proj.current_img = "page.png"

            proj.save()

            with open(proj.proj_path, "r", encoding="utf8") as f:
                saved = json.load(f)
            nested = saved["pages"]["page.png"][0]["region_inpaint_dict"]["source_block"]
            self.assertEqual(nested["text"], ["nested"])

    def test_project_load_prefers_separate_glossary_json_over_legacy_field(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = osp.join(tmpdir, "imgtrans_test.json")
            with open(project_path, "w", encoding="utf8") as f:
                json.dump(
                    {
                        "directory": tmpdir,
                        "pages": {},
                        "current_img": None,
                        "image_info": {},
                        "glossary": {"entries": "legacy => global", "prompt": "Legacy"},
                    },
                    f,
                )
            with open(osp.join(tmpdir, "glossary.json"), "w", encoding="utf8") as f:
                json.dump(
                    {"entries": "project => local [term]", "prompt": "Project only"},
                    f,
                    ensure_ascii=False,
                )

            proj = ProjImgTrans()
            proj.load(tmpdir, json_path=project_path)

            self.assertEqual(proj.glossary["entries"], "project => local [term]")
            self.assertEqual(proj.glossary["prompt"], "Project only")


if __name__ == "__main__":
    unittest.main()
