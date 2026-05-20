import json
import os.path as osp
import sys
import tempfile
import unittest

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.glossary_template import (
    build_glossary_from_project_text,
    build_glossary_from_translated_folder,
    classify_reference_term,
    extract_reference_terms,
    merge_glossary_entry_text,
)


class GlossaryTemplateTest(unittest.TestCase):
    def test_extracts_names_places_and_titles_from_english_text(self):
        terms = dict(extract_reference_terms("Lady Aria returned to Moonfall City with Captain Brant."))

        self.assertEqual(terms["Lady Aria"], "title")
        self.assertEqual(terms["Moonfall City"], "place")
        self.assertEqual(terms["Captain Brant"], "title")

    def test_scans_project_json_and_subfolders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chapter = osp.join(tmpdir, "chapter-02")
            import os

            os.makedirs(chapter)
            with open(osp.join(chapter, "imgtrans_chapter-02.json"), "w", encoding="utf8") as f:
                json.dump(
                    {
                        "pages": {
                            "001.png": [
                                {
                                    "text": "source text",
                                    "translation": "Mira reached North Gate Academy.",
                                }
                            ]
                        }
                    },
                    f,
                )

            top_only = build_glossary_from_translated_folder(tmpdir, include_subfolders=False)
            recursive = build_glossary_from_translated_folder(tmpdir, include_subfolders=True)

            self.assertEqual(top_only["entries"], "")
            self.assertIn("Mira => Mira [character]", recursive["entries"])
            self.assertIn("North Gate Academy => North Gate Academy", recursive["entries"])

    def test_imports_existing_glossary_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(osp.join(tmpdir, "glossary.json"), "w", encoding="utf8") as f:
                json.dump({"entries": "灯里 => Akari [character] # official spelling"}, f)

            glossary = build_glossary_from_translated_folder(tmpdir)

            self.assertIn("灯里 => Akari [character] # official spelling", glossary["entries"])

    def test_classifies_unknown_short_names_as_character(self):
        self.assertEqual(classify_reference_term("Akari"), "character")

    def test_builds_glossary_from_current_project_ocr_text(self):
        class Block:
            def __init__(self, text):
                self.text = text

            def get_text(self):
                return self.text

        class Project:
            pages = {
                "001.png": [Block("Akari met Professor Willow near Harbor City.")],
                "002.png": [Block("Akari returned to Harbor City.")],
            }

        glossary = build_glossary_from_project_text(Project())

        self.assertIn("Akari => Akari [character] # gloss scan: 001.png", glossary["entries"])
        self.assertIn("Professor Willow => Professor Willow [title]", glossary["entries"])
        self.assertIn("Harbor City => Harbor City [place]", glossary["entries"])
        self.assertEqual(glossary["entries"].count("Harbor City => Harbor City"), 1)

    def test_merges_glossary_text_without_overwriting_existing_terms(self):
        merged = merge_glossary_entry_text(
            "Akari => Official Akari [character] # hand edited",
            "Akari => Akari [character]\nHarbor City => Harbor City [place]",
        )

        self.assertIn("Official Akari", merged)
        self.assertNotIn("Akari => Akari [character]", merged)
        self.assertIn("Harbor City => Harbor City [place]", merged)


if __name__ == "__main__":
    unittest.main()
