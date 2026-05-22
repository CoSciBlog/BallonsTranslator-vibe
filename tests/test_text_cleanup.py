import unittest

from utils.text_cleanup import remove_translation_linebreaks


class TextCleanupTest(unittest.TestCase):
    def test_removes_common_linebreaks_from_translation_text(self):
        self.assertEqual(
            remove_translation_linebreaks("Thanks\nto\r\nthis\rI can rest"),
            "Thanks to this I can rest",
        )

    def test_preserves_text_without_linebreaks(self):
        self.assertEqual(
            remove_translation_linebreaks("Already one line."),
            "Already one line.",
        )


if __name__ == "__main__":
    unittest.main()
