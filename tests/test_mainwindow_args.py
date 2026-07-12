import os
import sys
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(APP_ROOT)

from ballontranslator.ui import mainwindow
from ballontranslator.ui.misc import parse_stylesheet


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

    def test_parse_stylesheet_accepts_legacy_reverse_icon_argument(self):
        stylesheet = parse_stylesheet("eva-light", reverse_icon=False)

        self.assertIsInstance(stylesheet, str)
        self.assertIn("QWidget", stylesheet)


if __name__ == "__main__":
    unittest.main()
