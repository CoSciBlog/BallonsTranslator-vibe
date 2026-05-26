import unittest
import os
import re
import sys

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.glossary_replacement import (
    apply_glossary_replacements_to_text,
    apply_replacements_to_glossary_targets,
    apply_replacements_to_preferred_targets,
    build_glossary_replacements,
    build_preferred_target_replacements,
    count_glossary_matches,
    parse_preferred_targets,
    replace_glossary_matches,
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

    def test_counts_and_replaces_selected_glossary_columns(self):
        glossary = {
            "entries": "スイレン => Suinen [character] # heroine",
            "reference_entries": "スイレン => Suinen [character]",
        }
        pattern = re.compile("Suinen")

        self.assertEqual(count_glossary_matches(glossary, pattern, False, True), 2)
        updated, count = replace_glossary_matches(glossary, pattern, "Suiren", False, True)

        self.assertEqual(count, 2)
        self.assertEqual(
            updated["entries"],
            "スイレン => Suiren [character] # heroine",
        )
        self.assertEqual(
            updated["reference_entries"],
            "スイレン => Suiren [character]",
        )

    def test_glossary_source_replacement_does_not_change_targets(self):
        glossary = {"entries": "Alice => Alice [character]"}
        pattern = re.compile("Alice")

        updated, count = replace_glossary_matches(glossary, pattern, "Alicia", True, False)

        self.assertEqual(count, 1)
        self.assertEqual(updated["entries"], "Alicia => Alice [character]")

    def test_preferred_target_rename_updates_translations_and_glossary_targets(self):
        old_glossary = {"preferred_targets": "Nemona [character]\nPaldea [place]"}
        new_glossary = {"preferred_targets": "NEMONA [character]\nPaldea [place]"}

        replacements = build_preferred_target_replacements(old_glossary, new_glossary)
        updated, count = apply_replacements_to_glossary_targets(
            {"entries": "ネモ => Nemona [character]", "reference_entries": ""},
            replacements,
        )
        text, text_count = apply_glossary_replacements_to_text(
            "Nemona visits Paldea.", replacements
        )

        self.assertEqual(replacements, [("Nemona", "NEMONA")])
        self.assertEqual(updated["entries"], "ネモ => NEMONA [character]")
        self.assertEqual(count, 1)
        self.assertEqual(text, "NEMONA visits Paldea.")
        self.assertEqual(text_count, 1)

    def test_preferred_targets_are_target_only_and_search_replace_can_update_them(self):
        glossary = {"preferred_targets": "NEMONA [character] # official\nPaldea [place]"}
        parsed = parse_preferred_targets(glossary["preferred_targets"])
        pattern = re.compile("NEMONA")

        self.assertEqual(parsed[0]["target"], "NEMONA")
        self.assertNotIn("source", parsed[0])
        self.assertEqual(count_glossary_matches(glossary, pattern, False, True), 1)
        updated, count = replace_glossary_matches(glossary, pattern, "Nemona", False, True)
        self.assertEqual(count, 1)
        self.assertIn("Nemona [character] # official", updated["preferred_targets"])

    def test_glossary_target_rename_synchronizes_preferred_targets(self):
        updated, count = apply_replacements_to_preferred_targets(
            {"preferred_targets": "Nemona [character]\nPaldea [place]"},
            [("Nemona", "NEMONA")],
        )

        self.assertEqual(count, 1)
        self.assertEqual(updated["preferred_targets"], "NEMONA [character]\nPaldea [place]")


if __name__ == "__main__":
    unittest.main()
