import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtCore import QCoreApplication, QEvent
from qtpy.QtWidgets import QApplication

from ballontranslator.ui.configpanel import ConfigPanel, ModuleSettingsWidget


class ModuleSettingsConfigPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self) -> None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        super().tearDown()

    def test_module_pages_are_available_in_modules_section(self) -> None:
        panel = ConfigPanel()
        self.addCleanup(panel.deleteLater)

        self.assertTrue(
            {'textdetector', 'ocr', 'inpainter'}.issubset(
                panel.configContent.section_index
            )
        )
        self.assertEqual(
            set(panel.module_settings_widgets),
            {'textdetector', 'ocr', 'inpainter'},
        )

    def test_selection_and_parameter_edits_include_module_identity(self) -> None:
        editor = ModuleSettingsWidget(
            'textdetector', ['ctd', 'other'], 'ctd', None
        )
        self.addCleanup(editor.deleteLater)
        selections = []
        edits = []
        editor.module_selected.connect(
            lambda module_type, name: selections.append((module_type, name))
        )
        editor.paramwidget_edited.connect(
            lambda *args: edits.append(args)
        )

        params = {
            'detect_size': {
                'type': 'selector',
                'options': [1024, 1280],
                'value': 1280,
            }
        }
        editor.setModule('ctd', params)
        editor.param_widget.paramwidget_edited.emit(
            'detect_size', {'content': '1024'}
        )
        editor.module_selector.setCurrentText('other')

        self.assertEqual(selections, [('textdetector', 'other')])
        self.assertEqual(
            edits,
            [('textdetector', 'ctd', 'detect_size', {'content': '1024'})],
        )

    def test_empty_module_parameters_show_safe_fallback(self) -> None:
        editor = ModuleSettingsWidget('ocr', ['manga_ocr'], 'manga_ocr', None)
        self.addCleanup(editor.deleteLater)

        editor.setModule('manga_ocr', {})

        self.assertIsNone(editor.param_widget)
        self.assertFalse(editor.empty_label.isHidden())


if __name__ == '__main__':
    unittest.main()
