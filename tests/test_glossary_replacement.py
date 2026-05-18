import unittest
import os
import sys

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.glossary_replacement import (
    apply_glossary_replacements_to_text,
    build_glossary_replacements,
)


class GlossaryReplacementTest(unittest.TestCase):
    def test_builds_replacement_for_changed_target_by_source(self):
        old_glossary = {"entries": "スイレン => Suinen [character]"}
        new_glossary = {"entries": "スイレン => Suiren [character]"}

        self.assertEqual(
            build_glossary_replacements(old_glossary, new_glossary),
            [("Suinen", "Suiren")],
        )

    def test_applies_replacement_without_touching_substrings(self):
        text, count = apply_glossary_replacements_to_text(
            "Suinen speaks. Suinenette does not.",
            [("Suinen", "Suiren")],
        )

        self.assertEqual(text, "Suiren speaks. Suinenette does not.")
        self.assertEqual(count, 1)

    def test_applies_escaped_html_replacement(self):
        text, count = apply_glossary_replacements_to_text(
            "<p>Tom &amp; Jerry arrived.</p>",
            [("Tom & Jerry", "Tom and Jerry")],
        )

        self.assertEqual(text, "<p>Tom and Jerry arrived.</p>")
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
