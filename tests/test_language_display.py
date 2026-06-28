import os.path as osp
import sys
import unittest

sys.path.insert(0, osp.dirname(osp.dirname(__file__)))

from modules.translators.base import LANGUAGE_ENGLISH_NAMES, lang_display_label, lang_display_to_key


class LanguageDisplayTest(unittest.TestCase):
    def test_english_is_available_for_language_selectors(self):
        self.assertIn("English", LANGUAGE_ENGLISH_NAMES)
        self.assertEqual(lang_display_label("English"), "English")
        self.assertEqual(lang_display_to_key("English"), "English")


if __name__ == "__main__":
    unittest.main()
