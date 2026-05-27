import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.module_manager import ImgtransThread


class SelectedTranslationReviewTest(unittest.TestCase):
    def test_review_mode_runs_review_without_ocr_or_inpainting(self):
        blocks = [Mock(), Mock()]
        dummy_thread = type("DummyThread", (), {})()
        dummy_thread.blktrans_page_key = "page.png"
        dummy_thread._review_textblocks = Mock()
        dummy_thread.finish_blktrans = Mock()

        ImgtransThread._blktrans_pipeline(dummy_thread, blocks, None, -2, [1, 3], None)

        dummy_thread._review_textblocks.assert_called_once_with("page.png", blocks)
        dummy_thread.finish_blktrans.emit.assert_called_once_with(-2, [1, 3])

    def test_shortening_mode_runs_rewrite_without_ocr_or_inpainting(self):
        blocks = [Mock(), Mock()]
        dummy_thread = type("DummyThread", (), {})()
        dummy_thread.blktrans_page_key = "page.png"
        dummy_thread._shorten_textblocks = Mock()
        dummy_thread.finish_blktrans = Mock()

        ImgtransThread._blktrans_pipeline(dummy_thread, blocks, None, -3, [1, 3], None)

        dummy_thread._shorten_textblocks.assert_called_once_with("page.png", blocks)
        dummy_thread.finish_blktrans.emit.assert_called_once_with(-3, [1, 3])


if __name__ == "__main__":
    unittest.main()
