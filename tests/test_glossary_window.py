import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from ballontranslator.glossary import GlossaryCategory, GlossaryStatus, GlossaryWorkspace
from ballontranslator.ui.configpanel import ConfigPanel
from ballontranslator.ui.glossary_window import GlossaryEntryDialog, GlossaryWindow
from ballontranslator.utils.config import pcfg


class GlossaryWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1] / 'tmp'
        root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temporary.cleanup)
        self.workspace = GlossaryWorkspace.for_project(self.temporary.name)
        self.addCleanup(self.workspace.close)
        self.window = GlossaryWindow()
        self.addCleanup(self.window.close)
        self.window.set_workspace(self.workspace)

    def test_entry_dialog_exposes_aliases_and_review_fields(self) -> None:
        dialog = GlossaryEntryDialog()
        self.addCleanup(dialog.deleteLater)
        dialog.original.setText('勇者')
        dialog.translation.setText('Hero')
        dialog.aliases.setText('勇者様, Yuusha')
        dialog.status.setCurrentText(GlossaryStatus.CONFIRMED.value)
        values = dialog.values()
        self.assertEqual(values['aliases'], ('勇者様', 'Yuusha'))
        self.assertEqual(values['status'], GlossaryStatus.CONFIRMED.value)

    def test_manager_contains_only_project_management_tabs(self) -> None:
        self.assertEqual(
            [self.window.tabs.tabText(index) for index in range(self.window.tabs.count())],
            ['Entries', 'Sources', 'Conflicts'],
        )
        self.assertFalse(hasattr(self.window, 'enabled_setting'))

    def test_settings_panel_owns_and_updates_glossary_configuration(self) -> None:
        names = (
            'project_glossary_enabled',
            'project_glossary_auto_create',
            'project_glossary_auto_extract',
            'project_glossary_review_enabled',
            'project_glossary_series_enabled',
            'project_glossary_conflict_warnings',
            'project_glossary_confirmation_mode',
            'project_glossary_max_prompt_entries',
            'project_glossary_detection_categories',
        )
        previous = {name: getattr(pcfg.module, name) for name in names}
        pcfg.module.project_glossary_enabled = False
        pcfg.module.project_glossary_confirmation_mode = 'manual'
        pcfg.module.project_glossary_max_prompt_entries = 25
        pcfg.module.project_glossary_detection_categories = [
            GlossaryCategory.CHARACTER.value
        ]
        panel = ConfigPanel()
        self.addCleanup(panel.close)
        try:
            self.assertIn('glossary', panel.configContent.section_index)
            panel.showSection('glossary')
            panel.show()
            self.app.processEvents()
            self.assertEqual(
                panel.configContent.currentIndex(),
                panel.configContent.section_index['glossary'],
            )
            self.assertEqual(panel.configTable.section_items['glossary'].text(), 'Glossary')
            self.assertTrue(panel.glossary_categories_list.isVisible())
            self.assertFalse(panel.glossary_enabled_checker.isChecked())
            self.assertEqual(panel.glossary_confirmation_combobox.currentIndex(), 0)
            self.assertEqual(panel.glossary_max_terms_spinbox.value(), 25)

            panel.glossary_enabled_checker.click()
            panel.glossary_confirmation_combobox.setCurrentIndex(1)
            panel.glossary_max_terms_spinbox.setValue(75)
            place_item = panel.glossary_categories_list.item(1)
            place_item.setCheckState(Qt.CheckState.Checked)

            self.assertTrue(pcfg.module.project_glossary_enabled)
            self.assertEqual(
                pcfg.module.project_glossary_confirmation_mode,
                'automatic',
            )
            self.assertEqual(pcfg.module.project_glossary_max_prompt_entries, 75)
            self.assertEqual(
                pcfg.module.project_glossary_detection_categories,
                [GlossaryCategory.CHARACTER.value, GlossaryCategory.PLACE.value],
            )
        finally:
            panel.close()
            for name, value in previous.items():
                setattr(pcfg.module, name, value)

    def test_table_confirm_reject_protect_and_delete(self) -> None:
        entry = self.workspace.project.create_entry(original='Alice', translation='Alice')
        self.window.refresh()
        self.window.entry_table.selectRow(0)
        self.window._confirm_entry()
        self.assertEqual(self.workspace.project.get_entry(entry.id).status, GlossaryStatus.CONFIRMED)
        self.window.entry_table.selectRow(0)
        self.window._toggle_protection()
        self.assertTrue(self.workspace.project.get_entry(entry.id).protected)
        self.window.entry_table.selectRow(0)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            self.window._delete_entry()
        self.assertEqual(self.workspace.project.entries, ())

    def test_sources_and_conflicts_are_visible(self) -> None:
        series = self.workspace.assign_series(Path(self.temporary.name) / 'series_glossary.json')
        self.workspace.project.create_entry(
            original='Sakura', translation='Project', status='Confirmed'
        )
        series.service.create_entry(
            original='Sakura', translation='Series', status='Confirmed'
        )
        self.window.refresh()
        self.assertEqual(self.window.sources_list.count(), 2)
        self.assertEqual(self.window.conflict_table.rowCount(), 2)

    def test_add_edit_and_json_exchange_use_project_service(self) -> None:
        fake = Mock()
        fake.exec_.return_value = QDialog.Accepted
        fake.values.return_value = {
            'original': 'Hero', 'translation': 'Held',
            'source_language': 'English', 'target_language': 'Deutsch',
            'category': 'Character', 'aliases': ('Brave',),
            'description': '', 'status': 'Confirmed', 'protected': False,
        }
        with patch(
            'ballontranslator.ui.glossary_window.GlossaryEntryDialog',
            return_value=fake,
        ):
            self.window._run_entry_dialog(self.workspace.project)
        entry = self.workspace.project.entries[0]
        self.assertEqual(entry.aliases, ('Brave',))

        export_path = Path(self.temporary.name) / 'export.json'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(export_path), '')):
            self.window._export_glossary()
        self.assertTrue(export_path.exists())

        self.workspace.project.delete_entry(entry.id)
        with (
            patch.object(QFileDialog, 'getOpenFileName', return_value=(str(export_path), '')),
            patch.object(QMessageBox, 'information'),
        ):
            self.window._import_glossary()
        self.assertEqual(self.workspace.project.entries[0].original, 'Hero')


if __name__ == '__main__':
    unittest.main()
