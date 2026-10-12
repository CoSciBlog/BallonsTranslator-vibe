import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtCore import QRectF
from qtpy.QtWidgets import QApplication

from ballontranslator.ui.text_engine.editing.manager import SceneTextManager
from ballontranslator.ui.text_engine.item import TextBlkItem
from ballontranslator.utils.config import pcfg
from ballontranslator.utils.text_layout import fit_textbox_rect_to_bounds
from ballontranslator.utils.textblock import TextBlock


class TextboxBoundsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_box_is_clamped_to_page_edges(self) -> None:
        fitted = fit_textbox_rect_to_bounds([-20, 80, 60, 40], 100, 100)

        self.assertEqual(fitted, [0, 60, 60, 40])

    def test_box_is_limited_to_speech_bubble_with_padding(self) -> None:
        fitted = fit_textbox_rect_to_bounds(
            [10, 15, 90, 30],
            200,
            100,
            bounds=[20, 10, 50, 40],
            inset=2,
        )

        self.assertEqual(fitted, [22, 15, 46, 30])

    def test_invalid_bubble_bounds_fall_back_to_page(self) -> None:
        fitted = fit_textbox_rect_to_bounds(
            [250, -30, 80, 50],
            200,
            100,
            bounds=[240, -40, 60, 20],
            inset=2,
        )

        self.assertEqual(fitted, [118, 2, 80, 50])

    def test_auto_layout_does_not_clip_content_at_bubble_bounds(self) -> None:
        item = TextBlkItem(
            TextBlock(
                xyxy=[0, 0, 20, 20],
                lines=[[[0, 0], [20, 0], [20, 20], [0, 20]]],
                translation='Hello world',
            ),
            0,
        )
        manager = SimpleNamespace(
            imgtrans_proj=SimpleNamespace(
                img_array=np.zeros((400, 200, 3), dtype=np.uint8)
            ),
            pairwidget_list=[],
            auto_textlayout_flag=True,
        )
        bubble_rect = [20, 10, 50, 40]
        padding = float(np.ceil(item.padding()))
        constrained = QRectF(*fit_textbox_rect_to_bounds(
            [10, 15, 90, 30],
            200,
            400,
            bounds=bubble_rect,
            inset=padding,
        ))

        with (
            patch.multiple(
                pcfg,
                let_autolayout_fit_bubble_flag=True,
                let_autolayout_no_linebreak_flag=True,
                remove_translation_line_breaks=False,
                let_fntsize_flag=1,
            ),
            patch.object(pcfg.module, 'translate_target', 'English'),
            patch(
                'ballontranslator.ui.text_engine.editing.manager.layout_text',
                return_value=(
                    'Hello\nworld',
                    [10, 15, 90, 30],
                    False,
                    False,
                ),
            ),
        ):
            changed = SceneTextManager.layout_textblk(
                manager,
                item,
                text='Hello world',
                mask=np.ones((40, 50), dtype=np.uint8),
                bounding_rect=[0, 0, 100, 80],
                region_rect=bubble_rect,
            )

        self.assertTrue(changed)
        self.assertEqual(item.toPlainText(), 'Hello world')
        min_height, min_width = item.layout.minSize()
        logical_rect = item.absBoundingRect(qrect=True)
        self.assertGreaterEqual(
            logical_rect.width(),
            min_width + padding * 2,
        )
        self.assertGreaterEqual(
            logical_rect.height(),
            min_height + padding * 2,
        )
        self.assertGreater(logical_rect.height(), constrained.height())
        self.assertGreaterEqual(logical_rect.left(), 0)
        self.assertGreaterEqual(logical_rect.top(), 0)
        self.assertLessEqual(logical_rect.right(), 200)
        self.assertLessEqual(logical_rect.bottom(), 400)


if __name__ == '__main__':
    unittest.main()
