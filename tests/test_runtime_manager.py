import os.path as osp
import sys
import unittest
from unittest.mock import patch

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from tools import runtime_manager


class RuntimeManagerTest(unittest.TestCase):
    def test_run_pip_install_enables_live_progress(self):
        calls = []

        def fake_run_command(command, logger, cwd=runtime_manager.ROOT, check=False, live=False):
            calls.append((command, check, live))

            class Result:
                returncode = 0

            return Result()

        with patch.object(runtime_manager, "run_command", side_effect=fake_run_command):
            runtime_manager.run_pip(["install", "torch"], runtime_manager.install_logger)

        command, check, live = calls[0]
        self.assertTrue(live)
        self.assertTrue(check)
        self.assertIn("--progress-bar", command)
        self.assertIn("on", command)

    def test_blackwell_profile_force_reinstalls_cuda_torch_wheels(self):
        pip_calls = []

        def fake_run_pip(args, logger, check=True):
            pip_calls.append(args)

            class Result:
                returncode = 0

            return Result()

        with patch.object(runtime_manager, "detect_environment", return_value={"gpu_name": "RTX 5070 Ti"}), \
             patch.object(runtime_manager, "log_versions"), \
             patch.object(runtime_manager, "uninstall_runtime_packages"), \
             patch.object(runtime_manager, "install_base_requirements"), \
             patch.object(runtime_manager, "run_pip", side_effect=fake_run_pip):
            runtime_manager.install_profile("nvidia_blackwell_cu128")

        torch_installs = [
            args for args in pip_calls
            if "https://download.pytorch.org/whl/cu128" in args
        ]
        self.assertEqual(len(torch_installs), 1)
        self.assertIn("--force-reinstall", torch_installs[0])
        self.assertIn("--no-deps", torch_installs[0])
        self.assertIn("torch", torch_installs[0])
        self.assertIn("torchvision", torch_installs[0])
        self.assertIn("torchaudio", torch_installs[0])


if __name__ == "__main__":
    unittest.main()
