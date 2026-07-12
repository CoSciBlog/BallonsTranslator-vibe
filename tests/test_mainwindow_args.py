import os
import sys
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(APP_ROOT)

from ballontranslator.ui import mainwindow


class MainWindowArgsTest(unittest.TestCase):
    def test_shared_arg_enabled_tolerates_missing_args(self):
        old_args = mainwindow.shared.args
        try:
            mainwindow.shared.args = None
            self.assertFalse(mainwindow._shared_arg_enabled("export_translation_txt"))
            mainwindow.shared.args = SimpleNamespace(export_translation_txt=True)
            self.assertTrue(mainwindow._shared_arg_enabled("export_translation_txt"))
        finally:
            mainwindow.shared.args = old_args


if __name__ == "__main__":
    unittest.main()
