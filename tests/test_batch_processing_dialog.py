import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtCore import Qt
from qtpy.QtTest import QTest
from qtpy.QtWidgets import QApplication, QDialog

from ballontranslator.ui.batch_processing_dialog import BatchProcessingDialog
from ballontranslator.utils.batch_processing import collect_batch_project_dirs


class BatchProcessingDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.chapter = self.root / 'chapter'
        self.chapter.mkdir()
        (self.chapter / '001.png').write_bytes(b'image')
        self.dialog = BatchProcessingDialog()
        self.addCleanup(self.dialog.deleteLater)

    def test_typed_quoted_path_can_start_batch_without_folder_picker(self) -> None:
        self.dialog.show()
        self.dialog.folder_edit.setFocus()
        QTest.keyClicks(self.dialog.folder_edit, f'  "{self.root}"  ')
        QTest.keyClick(self.dialog.folder_edit, Qt.Key.Key_Return)

        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.dialog.options().root_directory, str(self.root))
        self.assertEqual(self.dialog.project_directories, [str(self.chapter)])

    def test_changed_invalid_path_cannot_reuse_previously_selected_projects(self) -> None:
        with patch(
            'ballontranslator.ui.batch_processing_dialog.QFileDialog.getExistingDirectory',
            return_value=str(self.root),
        ):
            self.dialog.folder_button.click()
        self.assertEqual(self.dialog.project_directories, [str(self.chapter)])

        self.dialog.folder_edit.setText(str(self.root / 'missing'))
        self.assertEqual(self.dialog.project_directories, [])
        with patch('ballontranslator.ui.batch_processing_dialog.QMessageBox.warning') as warning:
            self.dialog.accept()
        warning.assert_called_once()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Rejected)

    def test_scans_committed_input_once_and_not_on_each_keystroke(self) -> None:
        with patch(
            'ballontranslator.ui.batch_processing_dialog.collect_batch_project_dirs',
            wraps=collect_batch_project_dirs,
        ) as collect:
            QTest.keyClicks(self.dialog.folder_edit, str(self.root))
            collect.assert_not_called()
            self.dialog.folder_edit.editingFinished.emit()
            self.dialog.accept()
            collect.assert_called_once_with(str(self.root))
        self.assertEqual(self.dialog.project_directories, [str(self.chapter)])

    def test_clearing_input_discards_projects_and_prevents_start(self) -> None:
        self.dialog.folder_edit.setText(str(self.root))
        self.dialog.folder_edit.editingFinished.emit()
        self.dialog.folder_edit.clear()

        with patch('ballontranslator.ui.batch_processing_dialog.QMessageBox.warning') as warning:
            self.dialog.accept()
        warning.assert_called_once()
        self.assertEqual(self.dialog.project_directories, [])
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Rejected)

    def test_cancelled_picker_preserves_manually_entered_path(self) -> None:
        self.dialog.folder_edit.setText(str(self.root))
        with patch(
            'ballontranslator.ui.batch_processing_dialog.QFileDialog.getExistingDirectory',
            return_value='',
        ):
            self.dialog.folder_button.click()
        self.dialog.accept()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.dialog.project_directories, [str(self.chapter)])
