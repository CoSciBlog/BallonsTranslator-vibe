import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WindowsLauncherTests(unittest.TestCase):

    def test_launcher_never_falls_back_to_global_python(self) -> None:
        launcher = (ROOT / 'launch_win.bat').read_text(encoding='utf8')

        self.assertIn(r'set "PYTHON=%VENV_DIR%\Scripts\python.exe"', launcher)
        self.assertIn(r'set "UV_EXE=%UV_ROOT%\uv.exe"', launcher)
        self.assertNotRegex(launcher, r'(?im)^set\s+"?PYTHON=python\.exe"?\s*$')
        self.assertIn(r'scripts\bootstrap_windows.ps1', launcher)

    def test_python_pin_satisfies_project_version_range(self) -> None:
        pinned = (ROOT / '.python-version').read_text(encoding='utf8').strip()
        match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', pinned)

        self.assertIsNotNone(match)
        version = tuple(int(part) for part in match.groups())
        self.assertGreaterEqual(version[:2], (3, 8))
        self.assertLess(version[:2], (3, 13))

    def test_launcher_requires_the_pinned_virtual_environment(self) -> None:
        launcher = (ROOT / 'launch_win.bat').read_text(encoding='utf8')

        self.assertIn('(3, 12, 10)', launcher)
        self.assertIn('goto :unsupported_runtime', launcher)

    def test_bootstrap_keeps_uv_python_and_cache_inside_project(self) -> None:
        bootstrap = (ROOT / 'scripts' / 'bootstrap_windows.ps1').read_text(encoding='utf8')

        self.assertIn('UV_PYTHON_INSTALL_DIR', bootstrap)
        self.assertIn('UV_CACHE_DIR', bootstrap)
        self.assertIn('--managed-python', bootstrap)
        self.assertIn('--no-registry', bootstrap)
        self.assertIn('".venv"', bootstrap)
        self.assertNotIn('Remove-Item -LiteralPath $VenvDir', bootstrap)

    def test_installer_and_release_builder_use_the_shared_uv_bootstrap(self) -> None:
        installer = (ROOT / 'scripts' / 'install.ps1').read_text(encoding='utf8')
        builder = (ROOT / 'scripts' / 'build_win_minimal.ps1').read_text(encoding='utf8')

        self.assertIn('bootstrap_windows.ps1', installer)
        self.assertIn('bootstrap_windows.ps1', builder)
        self.assertIn('-Relocatable', builder)
        self.assertNotIn('python-$PythonVersion-embed-amd64.zip', builder)

    def test_unix_launcher_does_not_fall_back_to_system_python(self) -> None:
        launcher = (ROOT / 'launch.sh').read_text(encoding='utf8')

        self.assertIn('exec "$VENV_PYTHON"', launcher)
        self.assertNotIn('command -v python', launcher)


if __name__ == '__main__':
    unittest.main()
