import logging
import os.path as osp
import sys
import unittest

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from modules.translators.trans_llm_api import LLM_API_Translator, TranslationResponse


class LLMResponseNormalizationTest(unittest.TestCase):
    def normalize(self, data):
        return LLM_API_Translator._normalize_translation_response_data(data)

    def validate(self, data):
        return TranslationResponse.model_validate(self.normalize(data))

    def test_existing_translation_response_stays_valid(self):
        data = {"translations": [{"id": 1, "translation": "Hello"}]}

        normalized = self.normalize(data)
        response = TranslationResponse.model_validate(normalized)

        self.assertEqual(normalized, data)
        self.assertEqual(response.translations[0].translation, "Hello")

    def test_list_response_is_wrapped(self):
        response = self.validate([{"id": 1, "translation": "Hello"}])

        self.assertEqual(len(response.translations), 1)
        self.assertEqual(response.translations[0].id, 1)
        self.assertEqual(response.translations[0].translation, "Hello")

    def test_single_translation_dict_is_wrapped(self):
        response = self.validate({"id": 1, "translation": "Hello"})

        self.assertEqual(len(response.translations), 1)
        self.assertEqual(response.translations[0].translation, "Hello")

    def test_single_draft_dict_uses_draft_translation(self):
        normalized = self.normalize(
            {"id": 1, "source": "Hallo", "draft_translation": "Hello"}
        )
        response = TranslationResponse.model_validate(normalized)

        self.assertEqual(normalized["translations"][0]["translation"], "Hello")
        self.assertEqual(response.translations[0].translation, "Hello")

    def test_empty_dict_returns_empty_translation_response(self):
        logger = logging.getLogger("test_llm_response_normalization")

        with self.assertLogs(logger, level="WARNING") as captured:
            normalized = LLM_API_Translator._normalize_translation_response_data(
                {},
                logger,
            )
        response = TranslationResponse.model_validate(normalized)

        self.assertEqual(response.translations, [])
        self.assertIn(
            "LLM returned empty JSON object; falling back to draft translations where possible.",
            "\n".join(captured.output),
        )


if __name__ == "__main__":
    unittest.main()
