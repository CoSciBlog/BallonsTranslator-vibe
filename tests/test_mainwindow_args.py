import os
import sys
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(APP_ROOT)

from qtpy.QtWidgets import QApplication

def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


_APP = qapp()

from ballontranslator.ui import mainwindow
from ballontranslator.ui.custom_widget.message import ImgtransProgressMessageBox
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

    def test_progress_box_shows_only_active_pipeline_stages(self):
        box = ImgtransProgressMessageBox()
        try:
            box.set_visible_stage_bars(detect=True, ocr=True, inpaint=True, translate=True)

            self.assertTrue(box.detect_bar.isVisibleTo(box))
            self.assertTrue(box.ocr_bar.isVisibleTo(box))
            self.assertTrue(box.inpaint_bar.isVisibleTo(box))
            self.assertTrue(box.translate_bar.isVisibleTo(box))
            self.assertFalse(box.decensor_bar.isVisibleTo(box))

            box.set_visible_stage_bars(decensor=True)

            self.assertFalse(box.detect_bar.isVisibleTo(box))
            self.assertFalse(box.ocr_bar.isVisibleTo(box))
            self.assertFalse(box.inpaint_bar.isVisibleTo(box))
            self.assertFalse(box.translate_bar.isVisibleTo(box))
            self.assertTrue(box.decensor_bar.isVisibleTo(box))
        finally:
            box.deleteLater()


if __name__ == "__main__":
    unittest.main()
