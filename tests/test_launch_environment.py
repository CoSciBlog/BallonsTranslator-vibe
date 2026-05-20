import os
import os.path as osp
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

import launch


class LaunchEnvironmentTest(unittest.TestCase):
    def _args(self, **overrides):
        values = {
            "frozen": False,
            "update": False,
            "repair_runtime": False,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_skips_environment_prepare_on_normal_start_with_runtime_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = osp.join(tmpdir, ".runtime_profile.json")
            with open(state_file, "w", encoding="utf8") as f:
                f.write("{}")
            with patch.object(launch, "args", self._args()):
                self.assertFalse(launch.should_prepare_environment(state_file))

    def test_prepares_environment_on_first_start(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = osp.join(tmpdir, ".runtime_profile.json")
            with patch.object(launch, "args", self._args()):
                self.assertTrue(launch.should_prepare_environment(state_file))

    def test_prepares_environment_for_update_or_repair(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = osp.join(tmpdir, ".runtime_profile.json")
            with open(state_file, "w", encoding="utf8") as f:
                f.write("{}")
            with patch.object(launch, "args", self._args(update=True)):
                self.assertTrue(launch.should_prepare_environment(state_file))
            with patch.object(launch, "args", self._args(repair_runtime=True)):
                self.assertTrue(launch.should_prepare_environment(state_file))

    def test_force_runtime_check_env_opt_in(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = osp.join(tmpdir, ".runtime_profile.json")
            with open(state_file, "w", encoding="utf8") as f:
                f.write("{}")
            with patch.object(launch, "args", self._args()), patch.dict(os.environ, {"BALLOONTRANS_FORCE_RUNTIME_CHECK": "1"}):
                self.assertTrue(launch.should_prepare_environment(state_file))


if __name__ == "__main__":
    unittest.main()
