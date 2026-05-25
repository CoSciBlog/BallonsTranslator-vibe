import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.text_layout import fit_textbox_rect_to_bounds


class TextboxBoundsTest(unittest.TestCase):
    def test_box_is_clamped_to_page_edges(self):
        fitted = fit_textbox_rect_to_bounds([-20, 80, 60, 40], 100, 100)

        self.assertEqual(fitted, [0, 60, 60, 40])

    def test_box_is_limited_to_speech_bubble_with_padding(self):
        fitted = fit_textbox_rect_to_bounds(
            [10, 15, 90, 30],
            200,
            100,
            bounds=[20, 10, 50, 40],
            inset=2,
        )

        self.assertEqual(fitted, [22, 15, 46, 30])


if __name__ == "__main__":
    unittest.main()
