import json
import os.path as osp
import sys
import tempfile
import unittest

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from utils.glossary_template import (
    build_glossary_from_translated_folder,
    classify_reference_term,
    extract_reference_terms,
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


if __name__ == "__main__":
    unittest.main()
