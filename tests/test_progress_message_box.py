import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication, QWidget

from ballontranslator.ui.custom_widget.message import ImgtransProgressMessageBox


class ImgtransProgressMessageBoxTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_pipeline_progress_is_a_movable_native_dialog(self) -> None:
        parent = QWidget()
        dialog = ImgtransProgressMessageBox(parent)
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(parent.deleteLater)

        flags = dialog.windowFlags()
        self.assertEqual(
            flags & Qt.WindowType.WindowType_Mask,
            Qt.WindowType.Window,
        )
        self.assertTrue(flags & Qt.WindowType.WindowTitleHint)
        self.assertTrue(flags & Qt.WindowType.CustomizeWindowHint)
        self.assertFalse(flags & Qt.WindowType.FramelessWindowHint)
        self.assertFalse(flags & Qt.WindowType.WindowCloseButtonHint)
        self.assertEqual(dialog.windowTitle(), 'BallonsTranslator')
        dialog.show_fitted()
        self.app.processEvents()
        self.assertTrue(dialog.isWindow())
        self.assertTrue(dialog.isVisible())
        dialog.hide()


if __name__ == '__main__':
    unittest.main()
