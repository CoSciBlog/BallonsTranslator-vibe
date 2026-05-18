import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.translators.base import BaseTranslator
from utils.textblock import TextBlock


class FakeReviewTranslator(BaseTranslator):
    def review_translations(self, src_list, draft_list):
        return [f"{src}:{draft}:reviewed" for src, draft in zip(src_list, draft_list)]


class FakeUnsupportedTranslator(BaseTranslator):
    pass


class TranslationReviewTest(unittest.TestCase):
    def test_review_textblk_lst_updates_existing_translations(self):
        translator = object.__new__(FakeReviewTranslator)
        translator.name = "FakeReview"

        blocks = [
            TextBlock(text=["source one"], translation="draft one"),
            TextBlock(text=[""], translation="keep me"),
            TextBlock(text=["source two"], translation=""),
        ]

        translator.review_textblk_lst(blocks)

        self.assertEqual(blocks[0].translation, "source one:draft one:reviewed")
        self.assertEqual(blocks[1].translation, "keep me")
        self.assertEqual(blocks[2].translation, "source two:source two:reviewed")

    def test_supports_translation_review_reports_override(self):
        review_translator = object.__new__(FakeReviewTranslator)
        unsupported = object.__new__(FakeUnsupportedTranslator)

        self.assertTrue(review_translator.supports_translation_review())
        self.assertFalse(unsupported.supports_translation_review())


if __name__ == "__main__":
    unittest.main()
