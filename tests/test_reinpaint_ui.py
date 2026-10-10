import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtGui import QKeySequence
from qtpy.QtWidgets import QAction, QApplication, QMainWindow

from ballontranslator.ui.batch_processing_dialog import BatchProcessingDialog
from ballontranslator.ui.mainwindowbars import TitleBar


def _app():
    return QApplication.instance() or QApplication([])


def test_tools_menu_exposes_current_and_all_page_reinpainting():
    app = _app()
    window = QMainWindow()
    title_bar = TitleBar(window)
    actions = {
        action.text(): action
        for action in title_bar.findChildren(QAction)
    }

    assert 'Re-run Inpainting Current Page' in actions
    assert 'Re-run Inpainting All Pages' in actions
    assert actions['Re-run Inpainting Current Page'].shortcut() == QKeySequence(
        'Ctrl+Shift+I'
    )
    assert actions['Pipeline History'].shortcut() == QKeySequence(
        'Ctrl+Shift+H'
    )

    title_bar.deleteLater()
    window.deleteLater()
    app.processEvents()


def test_batch_dialog_exports_reinpaint_option():
    app = _app()
    dialog = BatchProcessingDialog()
    dialog.reinpaint_check.setChecked(True)

    assert dialog.options().rerun_inpaint is True

    dialog.deleteLater()
    app.processEvents()
