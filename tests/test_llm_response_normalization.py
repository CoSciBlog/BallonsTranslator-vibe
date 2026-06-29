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

    def test_missing_id_is_dropped(self):
        normalized = self.normalize({"translations": [{"translation": "Hello"}]})

        self.assertEqual(normalized, {"translations": []})

    def test_string_id_is_normalized_to_int(self):
        response = self.validate({"translations": [{"id": "7", "translation": "Hello"}]})

        self.assertEqual(response.translations[0].id, 7)

    def test_entry_without_translation_or_draft_is_dropped(self):
        normalized = self.normalize({"translations": [{"id": 1, "source": "Hallo"}]})

        self.assertEqual(normalized, {"translations": []})

    def test_list_valued_translation_is_coerced_to_string(self):
        response = self.validate(
            {
                "translations": [
                    {
                        "id": 5,
                        "translation": ["Se-sensei...?", "Se-sensei...?"],
                    }
                ]
            }
        )

        self.assertEqual(response.translations[0].translation, "Se-sensei...?")

    def test_multiple_list_translation_candidates_are_joined_without_duplicates(self):
        response = self.validate(
            {
                "translations": [
                    {
                        "id": 1,
                        "translation": ["First line", "Second line", "First line"],
                    }
                ]
            }
        )

        self.assertEqual(response.translations[0].translation, "First line\nSecond line")

    def test_non_string_translation_scalars_are_coerced_to_string(self):
        response = self.validate({"translations": [{"id": 1, "translation": 1234}]})

        self.assertEqual(response.translations[0].translation, "1234")

    def test_object_translation_uses_nested_translation_text(self):
        response = self.validate(
            {"translations": [{"id": 1, "translation": {"text": "Nested text"}}]}
        )

        self.assertEqual(response.translations[0].translation, "Nested text")

    def test_malformed_truncated_translation_json_recovers_complete_items(self):
        raw_json = (
            '{"translations":[{"id":1,"translation":"I don\'t like you at all... or do I?"},'
            '{"id":2,"translation":"Feels good?"},'
            '{"id":3,"translation":"Really?"},'
            '{"id":4,"translation":"Oh!"},'
            '{"id":5,"translation":"Huh?"},'
            '{"id":6,"translation":"Ah! Ah!"},'
            '{"id":7,"translation":"Yes."},'
            '{"id":8,"translation":"Oh!"},'
            '{"id":9,"translation:":3333333333333333333333333333333'
        )
        logger = logging.getLogger("test_malformed_truncated_translation_json")

        with self.assertLogs(logger, level="WARNING") as captured:
            data = LLM_API_Translator._loads_json_with_list_recovery(
                raw_json,
                "translations",
                logger,
            )
        response = TranslationResponse.model_validate(self.normalize(data))

        self.assertEqual(len(response.translations), 8)
        self.assertEqual(response.translations[0].translation, "I don't like you at all... or do I?")
        self.assertEqual(response.translations[-1].id, 8)
        self.assertIn(
            "Recovered 8 complete translations item(s) from malformed or truncated JSON response.",
            "\n".join(captured.output),
        )

    def test_truncated_translation_json_without_broken_tail_recovers_complete_items(self):
        raw_json = (
            '{"translations":[{"id":1,"translation":"One"},'
            '{"id":2,"translation":"Two"}'
        )

        data = LLM_API_Translator._loads_json_with_list_recovery(raw_json, "translations")
        response = TranslationResponse.model_validate(self.normalize(data))

        self.assertEqual([item.translation for item in response.translations], ["One", "Two"])


if __name__ == "__main__":
    unittest.main()
