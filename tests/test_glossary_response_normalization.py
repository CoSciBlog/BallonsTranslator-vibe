import os.path as osp
import sys
import unittest

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from modules.translators.trans_llm_api import GlossaryResponse, LLM_API_Translator


class FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)


class GlossaryResponseNormalizationTest(unittest.TestCase):
    def validate(self, payload):
        normalized = LLM_API_Translator._normalize_glossary_response_data(payload)
        return GlossaryResponse.model_validate(normalized)

    def test_entries_shape_remains_valid(self):
        response = self.validate(
            {"entries": [{"source": "友利", "target": "Tomori", "category": "name"}]}
        )

        self.assertEqual(len(response.entries), 1)
        self.assertEqual(response.entries[0].target, "Tomori")

    def test_list_is_wrapped_as_entries(self):
        response = self.validate(
            [{"source": "友利", "target": "Tomori", "category": "name"}]
        )

        self.assertEqual(len(response.entries), 1)
        self.assertEqual(response.entries[0].source, "友利")

    def test_single_entry_dict_is_wrapped(self):
        response = self.validate(
            {"source": "小亞當", "target": "Little Adam", "category": "name"}
        )

        self.assertEqual(len(response.entries), 1)
        self.assertEqual(response.entries[0].target, "Little Adam")

    def test_alternate_terms_key_is_wrapped(self):
        response = self.validate(
            {"terms": [{"source": "楽園", "target": "Garden of Eden", "category": "place"}]}
        )

        self.assertEqual(len(response.entries), 1)
        self.assertEqual(response.entries[0].category, "place")

    def test_empty_dict_returns_empty_entries_and_logs_warning(self):
        logger = FakeLogger()
        normalized = LLM_API_Translator._normalize_glossary_response_data({}, logger)
        response = GlossaryResponse.model_validate(normalized)

        self.assertEqual(response.entries, [])
        self.assertIn(
            "LLM returned empty glossary JSON object; no glossary entries were extracted.",
            logger.warnings,
        )


if __name__ == "__main__":
    unittest.main()
