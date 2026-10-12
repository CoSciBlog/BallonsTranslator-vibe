import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtCore import QCoreApplication, QEvent, Qt
from qtpy.QtWidgets import QApplication, QLabel

from ballontranslator.ui.configpanel import ConfigPanel


class PostMergeConfigLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.panel = ConfigPanel()
        self.panel.resize(1125, 900)
        self.panel.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.panel.close()
        self.panel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_post_merge_controls_use_dedicated_page(self) -> None:
        self.assertIn('post_merge', self.panel.configContent.section_index)

        self.panel.showSection('post_merge')
        self.app.processEvents()
        post_merge_content = self.panel.configContent.currentWidget().widget()
        typesetting_index = self.panel.configContent.section_index['typesetting']
        typesetting_content = self.panel.configContent.widget(
            typesetting_index
        ).widget()

        self.assertTrue(
            post_merge_content.isAncestorOf(self.panel.post_merge_checker)
        )
        self.assertTrue(
            post_merge_content.isAncestorOf(self.panel.post_merge_mode_combobox)
        )
        self.assertFalse(
            typesetting_content.isAncestorOf(self.panel.post_merge_checker)
        )

    def test_merge_direction_selector_is_below_its_labels(self) -> None:
        self.panel.showSection('post_merge')
        self.app.processEvents()
        selector = self.panel.post_merge_mode_combobox
        row = selector.parentWidget()
        labels = row.findChildren(
            QLabel,
            options=Qt.FindChildOption.FindDirectChildrenOnly,
        )

        self.assertTrue(labels)
        self.assertGreater(
            selector.geometry().top(),
            max(label.geometry().bottom() for label in labels),
        )
        scroll_area = self.panel.configContent.currentWidget()
        self.assertFalse(scroll_area.horizontalScrollBar().isVisible())
        self.assertEqual(scroll_area.horizontalScrollBar().maximum(), 0)


if __name__ == '__main__':
    unittest.main()
