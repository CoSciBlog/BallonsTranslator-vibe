import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.textbox_merge import join_textbox_texts, union_xywh_rects


class TextboxMergeHelpersTest(unittest.TestCase):
    def test_join_textbox_texts_skips_empty_entries(self):
        self.assertEqual(
            join_textbox_texts([" First ", "", None, "Second"]),
            "First\nSecond",
        )

    def test_union_xywh_rects_covers_all_boxes(self):
        self.assertEqual(
            union_xywh_rects([[10, 20, 30, 40], [25, 5, 15, 10], [0, 45, 5, 5]]),
            [0, 5, 40, 55],
        )


if __name__ == "__main__":
    unittest.main()
