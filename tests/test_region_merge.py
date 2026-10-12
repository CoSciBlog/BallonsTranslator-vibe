import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from ballontranslator.ui.module_manager import ModuleManager
from ballontranslator.utils.config import ModuleConfig
from ballontranslator.utils.merger import (
    merge_selected_shapes,
    perform_configured_merge,
)
from ballontranslator.utils.config import pcfg
from ballontranslator.utils.textblock import TextBlock


def merge_config(mode: str = 'HORIZONTAL') -> dict:
    return {
        'MERGE_MODE': mode,
        'READING_DIRECTION': 'LTR',
        'PER_LABEL_DIRECTIONS': {},
        'LABELS_TO_EXCLUDE_FROM_MERGE': set(),
        'LABEL_MERGE_STRATEGY': 'PREFER_SHORTER',
        'REQUIRE_SAME_LABEL': False,
        'USE_SPECIFIC_MERGE_GROUPS': False,
        'SPECIFIC_MERGE_GROUPS': [],
        'VERTICAL_MERGE_PARAMS': {
            'max_vertical_gap': 30,
            'min_width_overlap_ratio': 50,
            'overlap_epsilon': 1e-6,
        },
        'HORIZONTAL_MERGE_PARAMS': {
            'max_horizontal_gap': 30,
            'min_height_overlap_ratio': 50,
            'overlap_epsilon': 1e-6,
        },
        'ADVANCED_MERGE_OPTIONS': {
            'allow_negative_gap': True,
            'debug_mode': False,
        },
        'OUTPUT_SHAPE_TYPE': 'rectangle',
    }


class RegionMergeTests(unittest.TestCase):
    def test_selected_merge_preserves_order_and_adds_line_breaks(self):
        shapes = [
            {
                'xyxy': [25, 0, 45, 20],
                'lines': [[[25, 0], [45, 0], [45, 20], [25, 20]]],
                'text': ['first source'],
                'translation': 'First translation',
            },
            {
                'xyxy': [0, 0, 20, 20],
                'lines': [[[0, 0], [20, 0], [20, 20], [0, 20]]],
                'text': ['second source'],
                'translation': 'Second translation',
            },
        ]

        merged, removed = merge_selected_shapes(shapes)

        self.assertEqual(removed, 1)
        self.assertEqual(len(merged), 1)
        self.assertEqual(
            merged[0]['translation'],
            'First translation\n\nSecond translation',
        )
        self.assertEqual(
            TextBlock(**merged[0]).get_text(),
            'first source\n\nsecond source',
        )

    def test_selected_merge_rejects_distant_boxes(self):
        shapes = [
            {
                'xyxy': [0, 0, 20, 20],
                'text': ['near'],
                'translation': 'Near',
            },
            {
                'xyxy': [300, 0, 320, 20],
                'text': ['far'],
                'translation': 'Far',
            },
        ]

        merged, removed = merge_selected_shapes(shapes)

        self.assertEqual(removed, 0)
        self.assertEqual(merged, shapes)

    def test_selected_merge_uses_current_rectangles_not_stale_ocr_lines(self):
        shapes = [
            {
                'xyxy': [100, 80, 140, 110],
                '_bounding_rect': [100, 80, 40, 30],
                'lines': [[[0, 0], [10, 0], [10, 10], [0, 10]]],
                'text': ['one'],
                'translation': 'One',
            },
            {
                'xyxy': [145, 85, 180, 115],
                '_bounding_rect': [145, 85, 35, 30],
                'lines': [[[20, 0], [30, 0], [30, 10], [20, 10]]],
                'text': ['two'],
                'translation': 'Two',
            },
        ]

        merged, removed = merge_selected_shapes(shapes)

        self.assertEqual(removed, 1)
        self.assertEqual(merged[0]['xyxy'], [100.0, 80.0, 180.0, 115.0])
        self.assertEqual(
            merged[0]['_bounding_rect'],
            [100.0, 80.0, 80.0, 35.0],
        )
        self.assertEqual(merged[0]['angle'], 0.0)

    def test_selected_sidebar_merge_is_undoable(self):
        from qtpy.QtCore import QCoreApplication, QEvent
        from qtpy.QtWidgets import QApplication, QWidget

        from ballontranslator.ui import shared_widget as SW
        from ballontranslator.ui.canvas import Canvas
        from ballontranslator.ui.text_engine.editing.manager import (
            SceneTextManager,
            TextPanel,
        )
        from ballontranslator.utils import config as C, shared
        from ballontranslator.utils.fontformat import FontFormat
        from ballontranslator.utils.proj_imgtrans import ProjImgTrans

        app = QApplication.instance() or QApplication([])
        host = QWidget()
        canvas = Canvas(host)
        canvas.editor_index = 1
        project = ProjImgTrans()
        canvas.imgtrans_proj = project
        previous_active_format = C.active_format
        try:
            with (
                patch.object(SW, 'canvas', canvas),
                patch.object(
                    shared,
                    'register_view_widget',
                    lambda *_args: None,
                    create=True,
                ),
            ):
                panel = TextPanel(app, host)
                panel.formatpanel.global_format = FontFormat()
                manager = SceneTextManager(
                    app,
                    host,
                    canvas,
                    panel,
                    parent=host,
                )
                blocks = [
                    TextBlock(
                        [0, 0, 80, 40],
                        _bounding_rect=[0, 0, 80, 40],
                        text=['source one'],
                        translation='Translation one',
                    ),
                    TextBlock(
                        [0, 45, 80, 85],
                        _bounding_rect=[0, 45, 80, 40],
                        text=['source two'],
                        translation='Translation two',
                    ),
                ]
                project.pages = {'page.png': blocks}
                project.current_img = 'page.png'
                items = [manager.addTextBlock(block) for block in blocks]
                for item in items:
                    item.setSelected(True)
                manager.formatpanel.resolve_text_transform_edits_for_history_change()
                manager.updateTextBlkList()
                before_rects = [item.absBoundingRect() for item in items]
                from qtpy.QtCore import QRectF
                canvas.setSceneRect(QRectF(0, 0, 800, 800))
                old_positions = [item.logical_position() for item in items]
                from qtpy.QtCore import QPoint
                from qtpy.QtWidgets import QMenu
                from qtpy.QtTest import QSignalSpy
                merge_requests = QSignalSpy(canvas.merge_textboxes)
                with patch.object(QMenu, 'exec', new=lambda menu, _pos: next(
                    action for action in menu.actions() if action.text() == 'Merge Selected Text Boxes'
                )):
                    canvas.on_create_contextmenu(QPoint(), False)
                self.assertEqual(len(merge_requests), 1)
                with patch.object(QMenu, 'exec', new=lambda menu, _pos: next(
                    action for action in menu.actions() if action.text() == 'Separate overlapping text boxes'
                )):
                    canvas.on_create_contextmenu(QPoint(), False)
                first, second = [item.sceneBoundingRect() for item in items]
                self.assertFalse(first.adjusted(-7.9, -7.9, 7.9, 7.9).intersects(second))
                moved_positions = [item.logical_position() for item in items]
                manager.separate_selected_textboxes()
                self.assertEqual([item.logical_position() for item in items], moved_positions)
                canvas.undo_textedit()
                self.assertEqual([item.logical_position() for item in items], old_positions)
                canvas.text_undo_stack.clear()
                expected_union = [
                    min(rect[0] for rect in before_rects),
                    min(rect[1] for rect in before_rects),
                    max(rect[0] + rect[2] for rect in before_rects)
                    - min(rect[0] for rect in before_rects),
                    max(rect[1] + rect[3] for rect in before_rects)
                    - min(rect[1] for rect in before_rects),
                ]

                merged_item = manager.merge_selected_textboxes()

                self.assertIsNotNone(merged_item)
                self.assertEqual(
                    canvas.text_undo_stack.command(0).merged_rect,
                    expected_union,
                )
                self.assertEqual(len(manager.textblk_item_list), 1)
                self.assertEqual(
                    merged_item.toPlainText(),
                    'Translation one\n\nTranslation two',
                )
                self.assertEqual(
                    manager.pairwidget_list[0].e_source.toPlainText(),
                    'source one\n\nsource two',
                )
                self.assertEqual(
                    merged_item.absBoundingRect(),
                    expected_union,
                )
                manager.updateTextBlkList()
                self.assertEqual(len(project.pages['page.png']), 1)
                self.assertEqual(
                    project.pages['page.png'][0].translation,
                    'Translation one\n\nTranslation two',
                )
                self.assertEqual(
                    project.pages['page.png'][0].bounding_rect(),
                    expected_union,
                )
                canvas.undo_textedit()
                self.assertEqual(len(manager.textblk_item_list), 2)
                self.assertEqual(
                    [item.toPlainText() for item in manager.textblk_item_list],
                    ['Translation one', 'Translation two'],
                )
                manager.updateTextBlkList()
                self.assertEqual(len(project.pages['page.png']), 2)
                canvas.redo_textedit()
                self.assertEqual(len(manager.textblk_item_list), 1)
                self.assertEqual(
                    manager.textblk_item_list[0].toPlainText(),
                    'Translation one\n\nTranslation two',
                )
                import numpy as np
                project.img_array = np.zeros((800, 800, 3), dtype=np.uint8)
                with (
                    patch.object(pcfg, 'remove_translation_line_breaks', True),
                    patch.object(pcfg.module, 'translate_target', 'English'),
                    patch('ballontranslator.ui.text_engine.editing.manager.layout_text', return_value=(
                        'Hello\nworld', [0, 0, 100, 80], False, False,
                    )),
                ):
                    manager.layout_textblk(
                        manager.textblk_item_list[0], text='Hello world',
                        mask=np.ones((80, 100), dtype=np.uint8),
                        bounding_rect=[0, 0, 100, 80], region_rect=[0, 0, 100, 80],
                    )
                    self.assertEqual(manager.textblk_item_list[0].toPlainText(), 'Hello world')
                    self.assertEqual(manager.pairwidget_list[0].e_trans.toPlainText(), 'Hello world')
                    manager.updateTextBlkList()
                    self.assertEqual(project.pages['page.png'][0].translation, 'Hello world')
                canvas.clear_undostack(update_saved_step=True)
                manager.clearSceneTextitems()
                panel.deleteLater()
        finally:
            C.active_format = previous_active_format
            canvas.gv.deleteLater()
            host.deleteLater()
            QCoreApplication.sendPostedEvents(
                None,
                QEvent.Type.DeferredDelete,
            )
            app.processEvents()

    def test_merge_preserves_source_and_translation_content(self):
        shapes = [
            {
                'xyxy': [0, 0, 20, 20],
                'lines': [[[0, 0], [20, 0], [20, 20], [0, 20]]],
                'text': ['What'],
                'translation': 'What',
                'rich_text': '<p>What</p>',
                'label': 'balloon',
            },
            {
                'xyxy': [25, 0, 45, 20],
                'lines': [[[25, 0], [45, 0], [45, 20], [25, 20]]],
                'text': ['now?'],
                'translation': 'now?',
                'rich_text': '<p>now?</p>',
                'label': 'balloon',
            },
        ]

        merged, removed = perform_configured_merge(shapes, merge_config())

        self.assertEqual(removed, 1)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['text'], ['What', 'now?'])
        self.assertEqual(merged[0]['translation'], 'What now?')
        self.assertEqual(merged[0]['rich_text'], '')

    def test_merge_avoids_artificial_cjk_spacing(self):
        shapes = [
            {
                'xyxy': [0, 0, 20, 20],
                'lines': [[[0, 0], [20, 0], [20, 20], [0, 20]]],
                'translation': 'こん',
            },
            {
                'xyxy': [25, 0, 45, 20],
                'lines': [[[25, 0], [45, 0], [45, 20], [25, 20]]],
                'translation': 'にちは',
            },
        ]

        merged, _ = perform_configured_merge(shapes, merge_config())

        self.assertEqual(merged[0]['translation'], 'こんにちは')

    def test_compact_auto_reading_order_follows_merge_direction(self):
        shapes = [
            {
                'xyxy': [0, 25, 20, 45],
                'lines': [[[0, 25], [20, 25], [20, 45], [0, 45]]],
                'translation': 'second',
            },
            {
                'xyxy': [0, 0, 20, 20],
                'lines': [[[0, 0], [20, 0], [20, 20], [0, 20]]],
                'translation': 'first',
            },
        ]
        config = merge_config('VERTICAL')
        config['READING_DIRECTION'] = 'AUTO'

        merged, _ = perform_configured_merge(shapes, config)

        self.assertEqual(merged[0]['translation'], 'first second')

    def test_separation_can_move_the_first_selected_box_to_make_room(
        self,
    ) -> None:
        from qtpy.QtCore import QCoreApplication, QEvent, QRectF
        from qtpy.QtWidgets import QApplication, QWidget

        from ballontranslator.ui import shared_widget as SW
        from ballontranslator.ui.canvas import Canvas
        from ballontranslator.ui.text_engine.editing.manager import (
            SceneTextManager,
            TextPanel,
        )
        from ballontranslator.utils import config as C, shared
        from ballontranslator.utils.fontformat import FontFormat
        from ballontranslator.utils.proj_imgtrans import ProjImgTrans

        app = QApplication.instance() or QApplication([])
        host = QWidget()
        canvas = Canvas(host)
        canvas.editor_index = 1
        project = ProjImgTrans()
        canvas.imgtrans_proj = project
        previous_active_format = C.active_format
        try:
            with (
                patch.object(SW, 'canvas', canvas),
                patch.object(
                    shared,
                    'register_view_widget',
                    lambda *_args: None,
                    create=True,
                ),
            ):
                panel = TextPanel(app, host)
                panel.formatpanel.global_format = FontFormat()
                manager = SceneTextManager(
                    app,
                    host,
                    canvas,
                    panel,
                    parent=host,
                )
                blocks = [
                    TextBlock(
                        [65, 10, 185, 90],
                        _bounding_rect=[65, 10, 120, 80],
                        translation='First',
                    ),
                    TextBlock(
                        [65, 10, 185, 90],
                        _bounding_rect=[65, 10, 120, 80],
                        translation='Second',
                    ),
                ]
                project.pages = {'page.png': blocks}
                project.current_img = 'page.png'
                items = [manager.addTextBlock(block) for block in blocks]
                for item in items:
                    item.setSelected(True)
                canvas.setSceneRect(QRectF(0, 0, 250, 100))
                original_positions = [
                    item.logical_position() for item in items
                ]
                self.assertTrue(
                    items[0].sceneBoundingRect().intersects(
                        items[1].sceneBoundingRect()
                    )
                )

                manager.separate_selected_textboxes()

                first, second = [item.sceneBoundingRect() for item in items]
                self.assertFalse(
                    first.adjusted(-7.9, -7.9, 7.9, 7.9).intersects(second)
                )
                self.assertTrue(canvas.sceneRect().contains(first))
                self.assertTrue(canvas.sceneRect().contains(second))
                canvas.undo_textedit()
                self.assertEqual(
                    [item.logical_position() for item in items],
                    original_positions,
                )
                canvas.clear_undostack(update_saved_step=True)
                manager.clearSceneTextitems()
                panel.deleteLater()
        finally:
            C.active_format = previous_active_format
            host.deleteLater()
            QCoreApplication.sendPostedEvents(
                None,
                QEvent.Type.DeferredDelete,
            )
            app.processEvents()

    def test_invalid_persisted_settings_fall_back_safely(self):
        config = ModuleConfig(
            post_merge_textboxes='yes',
            post_merge_mode='DIAGONAL',
            post_merge_max_vertical_gap=-1,
            post_merge_max_horizontal_gap=1001,
            post_merge_min_width_overlap_ratio=101,
            post_merge_min_height_overlap_ratio=False,
        )

        self.assertFalse(config.post_merge_textboxes)
        self.assertEqual(config.post_merge_mode, 'VERTICAL_THEN_HORIZONTAL')
        self.assertEqual(config.post_merge_max_vertical_gap, 30)
        self.assertEqual(config.post_merge_max_horizontal_gap, 30)
        self.assertEqual(config.post_merge_min_width_overlap_ratio, 50)
        self.assertEqual(config.post_merge_min_height_overlap_ratio, 50)

    def test_post_pipeline_merge_only_changes_processed_pages(self):
        class Project:
            def __init__(self):
                self.pages = {
                    'processed.png': self._blocks(),
                    'untouched.png': self._blocks(),
                }

            @staticmethod
            def _blocks():
                return [
                    TextBlock(
                        xyxy=[0, 0, 20, 20],
                        lines=[[[0, 0], [20, 0], [20, 20], [0, 20]]],
                        translation='Hello',
                    ),
                    TextBlock(
                        xyxy=[25, 0, 45, 20],
                        lines=[[[25, 0], [45, 0], [45, 20], [25, 20]]],
                        translation='there',
                    ),
                ]

            def pipeline_pages(self, requested=None):
                if requested is None:
                    return list(self.pages)
                return [name for name in requested if name in self.pages]

            def pagename2idx(self, page_name):
                return list(self.pages).index(page_name)

        project = Project()
        processed_list = project.pages['processed.png']
        manager = ModuleManager(project)
        manager._pipeline_pages_to_process = ['processed.png']
        manager._post_pipeline_merge_done = False
        changed_pages = []
        manager.page_trans_finished.connect(changed_pages.append)

        with (
            patch.object(pcfg.module, 'post_merge_textboxes', True),
            patch.object(pcfg.module, 'post_merge_mode', 'HORIZONTAL'),
        ):
            removed = manager.apply_post_pipeline_textbox_merge()

        self.assertEqual(removed, 1)
        self.assertIs(project.pages['processed.png'], processed_list)
        self.assertEqual(len(project.pages['processed.png']), 1)
        self.assertEqual(len(project.pages['untouched.png']), 2)
        self.assertEqual(changed_pages, [0])


if __name__ == '__main__':
    unittest.main()
