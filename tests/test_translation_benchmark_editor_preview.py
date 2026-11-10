import copy
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import Image
from qtpy.QtCore import QCoreApplication, QEvent
from qtpy.QtWidgets import QApplication, QHBoxLayout, QStackedWidget, QWidget

from ballontranslator.ui import shared_widget as SW
from ballontranslator.ui.canvas import Canvas
from ballontranslator.ui.mainwindow import MainWindow
from ballontranslator.ui.mainwindowbars import LeftBar
from ballontranslator.ui.misc import parse_stylesheet
from ballontranslator.ui.text_engine.editing.manager import SceneTextManager, TextPanel
from ballontranslator.ui.text_engine.item import TextBlkItem
from ballontranslator.ui.translation_benchmark_results import (
    TranslationBenchmarkResultsWidget,
)
from ballontranslator.utils import config as C, shared
from ballontranslator.utils.fontformat import FontFormat
from ballontranslator.utils.llm_profiles import LLMProfile
from ballontranslator.utils.proj_imgtrans import ProjImgTrans
from ballontranslator.utils.textblock import TextBlock
from ballontranslator.utils.translation_benchmark import (
    TranslationBenchmarkReport,
    TranslationBenchmarkRun,
    TranslationBenchmarkVariant,
)


def _run(profile_id: str, translation: str) -> TranslationBenchmarkRun:
    profile = LLMProfile(
        id=profile_id,
        name=profile_id.upper(),
        model=f'{profile_id}-model',
    )
    block = TextBlock(
        [0, 0, 300, 120],
        _bounding_rect=[0, 0, 300, 120],
        text=['source'],
        translation=translation,
        fontformat=FontFormat(font_family='DejaVu Sans', font_size=24),
    )
    return TranslationBenchmarkRun(
        variant=TranslationBenchmarkVariant.from_profile(profile),
        translations={'01.png': [translation]},
        preview_pages={'01.png': [block]},
    )


def _report() -> TranslationBenchmarkReport:
    return TranslationBenchmarkReport(
        pages=['01.png'],
        sources={'01.png': ['source']},
        source_language='Japanese',
        target_language='English',
        text_detector='detector',
        ocr='ocr',
        detection_ocr_seconds=0.1,
        runs=[_run('one', 'first result'), _run('two', 'second result')],
    )


class _PreviewHost(QWidget):
    _set_left_panel_content = MainWindow._set_left_panel_content
    _sync_llm_context_editor_visibility = (
        MainWindow._sync_llm_context_editor_visibility
    )
    pageLabelStateChanged = MainWindow.pageLabelStateChanged
    on_set_gsearch_widget = MainWindow.on_set_gsearch_widget
    on_set_benchmark_results_widget = (
        MainWindow.on_set_benchmark_results_widget
    )
    _show_translation_benchmark_preview = (
        MainWindow._show_translation_benchmark_preview
    )
    _apply_translation_benchmark_preview = (
        MainWindow._apply_translation_benchmark_preview
    )
    _dismiss_translation_benchmark_preview = (
        MainWindow._dismiss_translation_benchmark_preview
    )
    _set_benchmark_preview_editing_locked = (
        MainWindow._set_benchmark_preview_editing_locked
    )
    _stop_translation_benchmark_preview = (
        MainWindow._stop_translation_benchmark_preview
    )


class TranslationBenchmarkEditorPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        Image.new('RGB', (400, 200), 'white').save(
            os.path.join(self.directory.name, '01.png')
        )
        Image.new('RGB', (400, 200), 'white').save(
            os.path.join(self.directory.name, '02.png')
        )
        self.project = ProjImgTrans(self.directory.name)
        self.project.set_current_img('01.png')
        block = TextBlock(
            [0, 0, 300, 120],
            _bounding_rect=[0, 0, 300, 120],
            text=['source'],
            translation='project translation',
            fontformat=FontFormat(font_family='DejaVu Sans', font_size=24),
        )
        self.project.pages['01.png'] = [block]
        second_page_block = copy.deepcopy(block)
        second_page_block.translation = 'second page project translation'
        self.project.pages['02.png'] = [second_page_block]

        self.host = _PreviewHost()
        self.canvas = Canvas(self.host)
        self.canvas.imgtrans_proj = self.project
        self.canvas.editor_index = 1
        self.sw_patch = patch.object(SW, 'canvas', self.canvas)
        self.sw_patch.start()
        self.addCleanup(self.sw_patch.stop)
        self.config_patch = patch.object(C, 'active_format', C.active_format)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.shared_patch = patch.object(
            shared, 'register_view_widget', create=True
        )
        self.shared_patch.start()
        self.addCleanup(self.shared_patch.stop)

        self.panel = TextPanel(self.app, self.host)
        self.panel.formatpanel.global_format = FontFormat()
        self.manager = SceneTextManager(
            self.app,
            self.host,
            self.canvas,
            self.panel,
            parent=self.host,
        )
        self.manager.populateSceneTextitems()
        self.stack = QStackedWidget(self.host)
        self.stack.addWidget(self.panel)

        self.host.pageList = QWidget(self.host)
        self.host.global_search_widget = QWidget(self.host)
        self.host.leftStackWidget = QStackedWidget(self.host)
        self.host.leftStackWidget.addWidget(self.host.pageList)
        self.host.leftStackWidget.addWidget(self.host.global_search_widget)
        self.host.benchmark_results_widget = (
            TranslationBenchmarkResultsWidget(self.host.leftStackWidget)
        )
        self.host.leftStackWidget.addWidget(
            self.host.benchmark_results_widget
        )
        self.host.llmContextEditor = SimpleNamespace(
            hide=lambda: None,
            show=lambda: None,
            set_context_visible=lambda _visible: None,
        )
        self.host.leftBar = LeftBar(self.host)
        self.host.leftBar.showPageListLabel.clicked.connect(
            self.host.pageLabelStateChanged
        )
        self.host.leftBar.globalSearchChecker.clicked.connect(
            self.host.on_set_gsearch_widget
        )
        self.host.leftBar.benchmarkResultsChecker.clicked.connect(
            self.host.on_set_benchmark_results_widget
        )
        self.host.benchmark_results_widget.preview_requested.connect(
            self.host._apply_translation_benchmark_preview
        )
        self.host.benchmark_results_widget.project_translation_requested.connect(
            self.host._stop_translation_benchmark_preview
        )

        layout = QHBoxLayout(self.host)
        layout.addWidget(self.host.leftBar)
        layout.addWidget(self.host.leftStackWidget)
        layout.addWidget(self.canvas.gv)
        layout.addWidget(self.stack)

        self.host.canvas = self.canvas
        self.host.st_manager = self.manager
        self.host.imgtrans_proj = self.project
        self.host.rightComicTransStackPanel = self.stack
        self.host._translation_benchmark_report = None
        self.host._benchmark_preview_view_interactive = True
        self.host._benchmark_preview_panel_enabled = True
        self.host.leftBar.showPageListLabel.setChecked(True)
        self.host._set_left_panel_content(self.host.pageList)
        self.host.resize(900, 500)
        self.host.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.host._dismiss_translation_benchmark_preview()
        self.canvas.clear_undostack(update_saved_step=True)
        self.manager.clearSceneTextitems()
        self.host.close()
        self.host.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def _visible_preview_texts(self):
        live_items = set(self.manager.textblk_item_list)
        return [
            item.toPlainText()
            for item in self.canvas.textLayer.childItems()
            if (
                isinstance(item, TextBlkItem)
                and item not in live_items
                and item.isVisible()
            )
        ]

    def test_switches_detached_results_without_changing_project_or_history(self) -> None:
        original_item = self.manager.textblk_item_list[0]
        original_count = self.canvas.text_undo_stack.count()
        report = _report()

        self.assertFalse(
            self.host.leftBar.benchmarkResultsChecker.isEnabled()
        )
        self.host._show_translation_benchmark_preview(report, 0)
        self.app.processEvents()

        self.assertTrue(
            self.host.leftBar.benchmarkResultsChecker.isEnabled()
        )
        self.assertTrue(
            self.host.leftBar.benchmarkResultsChecker.isChecked()
        )
        self.assertIs(
            self.host.leftStackWidget.currentWidget(),
            self.host.benchmark_results_widget,
        )
        self.assertTrue(self.manager.benchmark_preview_active)
        self.assertFalse(original_item.isVisible())
        self.assertFalse(self.canvas.gv.isInteractive())
        self.assertFalse(self.stack.isEnabled())
        self.assertEqual(self._visible_preview_texts(), ['first result'])

        self.host.benchmark_results_widget.results_list.setCurrentRow(1)
        self.app.processEvents()
        self.assertEqual(self._visible_preview_texts(), ['second result'])
        self.manager.updateTextBlkList()
        self.assertEqual(
            self.project.pages['01.png'][0].translation,
            'project translation',
        )
        self.assertEqual(self.canvas.text_undo_stack.count(), original_count)

        self.host.benchmark_results_widget.project_translation_button.click()
        self.app.processEvents()
        self.assertFalse(self.manager.benchmark_preview_active)
        self.assertTrue(original_item.isVisible())
        self.assertTrue(self.canvas.gv.isInteractive())
        self.assertTrue(self.stack.isEnabled())
        self.assertTrue(
            self.host.leftBar.benchmarkResultsChecker.isEnabled()
        )
        self.assertEqual(
            self.host.benchmark_results_widget.selected_run_index(),
            -1,
        )

    def test_missing_page_keeps_live_text_visible(self) -> None:
        report = _report()
        report.runs[0].preview_pages = {'other.png': report.runs[0].preview_pages['01.png']}
        report.runs[0].translations = {'other.png': ['first result']}
        self.host._show_translation_benchmark_preview(report, 0)
        self.app.processEvents()

        self.assertFalse(self.manager.benchmark_preview_active)
        self.assertTrue(self.manager.textblk_item_list[0].isVisible())
        self.assertEqual(
            self.host.benchmark_results_widget.page_status.text(),
            'No benchmark result for 01.png',
        )

    def test_selected_result_reapplies_after_page_change(self) -> None:
        report = _report()
        second_page_preview = copy.deepcopy(
            report.runs[1].preview_pages['01.png']
        )
        second_page_preview[0].translation = 'second page benchmark result'
        report.runs[1].preview_pages['02.png'] = second_page_preview
        report.runs[1].translations['02.png'] = [
            'second page benchmark result'
        ]
        self.host._show_translation_benchmark_preview(report, 1)

        self.manager.clearSceneTextitems()
        self.project.set_current_img('02.png')
        self.manager.populateSceneTextitems()
        self.host._apply_translation_benchmark_preview(1)
        self.app.processEvents()

        self.assertEqual(
            self._visible_preview_texts(),
            ['second page benchmark result'],
        )
        self.assertEqual(
            self.project.pages['02.png'][0].translation,
            'second page project translation',
        )

    def test_sidebar_switches_from_page_list_and_renders_in_both_themes(self) -> None:
        old_stylesheet = self.app.styleSheet()
        try:
            for theme in ('eva-light', 'eva-dark'):
                self.app.setStyleSheet(parse_stylesheet(theme))
                self.host._show_translation_benchmark_preview(_report(), 1)
                self.app.processEvents()
                self.assertEqual(
                    self.host.benchmark_results_widget.selected_run_index(),
                    1,
                )
                self.assertFalse(
                    self.host.benchmark_results_widget.grab().isNull()
                )
                self.assertIn(
                    'two-model',
                    self.host.benchmark_results_widget.results_list.item(1).text(),
                )
                self.host.leftBar.showPageListLabel.click()
                self.assertIs(
                    self.host.leftStackWidget.currentWidget(),
                    self.host.pageList,
                )
                self.assertFalse(
                    self.host.leftBar.benchmarkResultsChecker.isChecked()
                )
                self.assertTrue(self.manager.benchmark_preview_active)
                self.host.leftBar.benchmarkResultsChecker.click()
                self.assertIs(
                    self.host.leftStackWidget.currentWidget(),
                    self.host.benchmark_results_widget,
                )
                self.host._dismiss_translation_benchmark_preview()
                self.assertFalse(
                    self.host.leftBar.benchmarkResultsChecker.isEnabled()
                )
        finally:
            self.app.setStyleSheet(old_stylesheet)


if __name__ == '__main__':
    unittest.main()
