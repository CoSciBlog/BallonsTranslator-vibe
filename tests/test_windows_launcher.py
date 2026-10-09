import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WindowsLauncherTests(unittest.TestCase):

    def test_launcher_never_falls_back_to_global_python(self) -> None:
        launcher = (ROOT / 'launch_win.bat').read_text(encoding='utf8')

        self.assertIn(r'set "PYTHON=%RUNTIME_DIR%\python.exe"', launcher)
        self.assertNotRegex(launcher, r'(?im)^set\s+"?PYTHON=python\.exe"?\s*$')
        self.assertIn(r'scripts\install.ps1', launcher)

    def test_installer_python_satisfies_project_version_range(self) -> None:
        installer = (ROOT / 'scripts' / 'install.ps1').read_text(encoding='utf8')
        match = re.search(r'\$PythonVersion\s*=\s*"(\d+)\.(\d+)\.(\d+)"', installer)

        self.assertIsNotNone(match)
        version = tuple(int(part) for part in match.groups())
        self.assertGreaterEqual(version[:2], (3, 8))
        self.assertLess(version[:2], (3, 13))

    def test_launcher_rejects_unsupported_local_runtime(self) -> None:
        launcher = (ROOT / 'launch_win.bat').read_text(encoding='utf8')

        self.assertIn('(3, 8)', launcher)
        self.assertIn('(3, 12)', launcher)
        self.assertNotIn('(3, 13)', launcher)
        self.assertIn('goto :unsupported_runtime', launcher)


if __name__ == '__main__':
    unittest.main()
