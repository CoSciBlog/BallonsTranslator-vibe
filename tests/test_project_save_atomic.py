import json
import os
import os.path as osp
import sys
import tempfile
import unittest
from unittest.mock import patch

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.proj_imgtrans import safe_replace_with_retries


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


if __name__ == "__main__":
    unittest.main()
