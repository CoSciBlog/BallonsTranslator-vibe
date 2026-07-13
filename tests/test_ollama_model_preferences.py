import unittest

from utils.ollama import OLLAMA_DEFAULT_ENDPOINT, ollama_tags_endpoint
from utils.config import ModuleConfig


class OllamaModelPreferencesTest(unittest.TestCase):
    def test_default_tags_endpoint(self):
        self.assertEqual(
            ollama_tags_endpoint(OLLAMA_DEFAULT_ENDPOINT),
            'http://127.0.0.1:11434/api/tags',
        )

    def test_native_tags_endpoint_is_not_duplicated(self):
        self.assertEqual(
            ollama_tags_endpoint('http://server:11434/api/tags'),
            'http://server:11434/api/tags',
        )

    def test_preferences_are_serialized_in_translator_config(self):
        preferences = {
            'qwen3:8b': {'favorite': True, 'rating': 5},
            'gemma3:12b': {'favorite': False, 'rating': 3},
        }
        config = ModuleConfig(translator_params={
            'LLM_API_Translator': {
                'ollama model preferences': {'value': preferences},
            },
        })

        saved = config.get_saving_params()

        self.assertEqual(
            saved['translator_params']['LLM_API_Translator'][
                'ollama model preferences'
            ],
            preferences,
        )


if __name__ == '__main__':
    unittest.main()
