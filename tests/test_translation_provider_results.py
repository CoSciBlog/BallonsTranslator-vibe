import os.path as osp
import sys
import unittest

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from modules.translators.base import BaseTranslator
from modules.translators.trans_two_step import TwoStepTranslator
from utils.textblock import TextBlock


class FakeDirectTranslator(BaseTranslator):
    def __init__(self, name, outputs):
        self.name = name
        self.outputs = outputs

    def provider_result_label(self):
        return super().provider_result_label()


class FakeTwoStepTranslator(TwoStepTranslator):
    def __init__(self, provider="google"):
        self._provider = provider

    @property
    def first_step_translator(self):
        return self._provider


class TranslationProviderResultsTest(unittest.TestCase):
    def test_textblock_serializes_provider_results(self):
        block = TextBlock(text=["src"])
        block.translation_provider_results = {
            "Google": "google result",
            "DeepL": "deepl result",
        }
        block.translation_llm_review = "review result"

        dumped = block.to_dict()
        loaded = TextBlock(**dumped)

        self.assertEqual(
            loaded.translation_provider_results,
            {"Google": "google result", "DeepL": "deepl result"},
        )
        self.assertEqual(loaded.translation_llm_review, "review result")

    def test_direct_google_results_are_stored_without_clearing_deepl(self):
        blocks = [
            TextBlock(text=["one"]),
            TextBlock(text=["two"]),
        ]
        blocks[0].translation_provider_results = {"DeepL": "eins"}
        translator = FakeDirectTranslator("google", ["google one", "google two"])

        translator._store_provider_results(blocks, [0, 1], translator.outputs)

        self.assertEqual(blocks[0].translation_provider_results["DeepL"], "eins")
        self.assertEqual(blocks[0].translation_provider_results["Google"], "google one")
        self.assertEqual(blocks[1].translation_provider_results["Google"], "google two")
        self.assertEqual(blocks[0].translation_draft, "google one")
        self.assertEqual(blocks[1].translation_draft, "google two")

    def test_two_step_deepl_free_results_are_stored_with_provider_label(self):
        blocks = [TextBlock(text=["one"])]
        translator = FakeTwoStepTranslator("DeepL Free")

        translator._store_first_step_results(blocks, [0], ["deepl free result"])

        self.assertEqual(
            blocks[0].translation_provider_results,
            {"DeepL Free": "deepl free result"},
        )
        self.assertEqual(blocks[0].translation_draft, "deepl free result")


if __name__ == "__main__":
    unittest.main()
