import unittest

from utils.ollama import (
    OLLAMA_DEFAULT_ENDPOINT,
    ollama_model_matches_query,
    ollama_show_endpoint,
    ollama_tags_endpoint,
    ollama_thinking_capability,
)
from utils.config import ModuleConfig, migrate_ollama_translator_config


class OllamaModelPreferencesTest(unittest.TestCase):
    def test_model_search_matches_case_insensitive_multiple_terms(self):
        self.assertTrue(ollama_model_matches_query('Gemma3:12B-Latest', 'gemma 12b'))
        self.assertTrue(ollama_model_matches_query('qwen3.5:27b', 'QWEN3.5'))
        self.assertFalse(ollama_model_matches_query('gemma3:12b', 'gemma 27b'))

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

    def test_show_endpoint_and_thinking_capability(self):
        self.assertEqual(
            ollama_show_endpoint('http://server:11434/api/tags'),
            'http://server:11434/api/show',
        )
        self.assertTrue(ollama_thinking_capability(['completion', 'thinking']))
        self.assertFalse(ollama_thinking_capability(['completion', 'vision']))
        self.assertIsNone(ollama_thinking_capability(None))

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

    def test_existing_ollama_profiles_are_migrated(self):
        profiles = {
            'LLM_API_Translator': {
                'provider': 'Ollama',
                'endpoint': 'http://localhost:11434/v1',
            },
            'LLM_API_Translator_2': {
                'provider': 'OpenAI',
                'endpoint': '',
            },
            'Two-Step Translator': {
                'provider': 'Ollama',
            },
        }

        migrate_ollama_translator_config(profiles)

        self.assertEqual(
            profiles['LLM_API_Translator']['endpoint'],
            OLLAMA_DEFAULT_ENDPOINT,
        )
        self.assertEqual(
            profiles['Two-Step Translator']['endpoint'],
            OLLAMA_DEFAULT_ENDPOINT,
        )
        self.assertEqual(profiles['LLM_API_Translator_2']['endpoint'], '')
        for profile in profiles.values():
            self.assertEqual(profile['ollama model preferences'], {})

    def test_existing_preferences_and_custom_endpoint_are_preserved(self):
        preferences = {'qwen3:8b': {'favorite': True, 'rating': 5}}
        profiles = {
            'LLM_API_Translator': {
                'provider': 'Ollama',
                'endpoint': 'http://ollama.lan:11434/v1',
                'ollama model preferences': preferences,
            },
        }

        migrate_ollama_translator_config(profiles)

        self.assertEqual(
            profiles['LLM_API_Translator']['endpoint'],
            'http://ollama.lan:11434/v1',
        )
        self.assertIs(
            profiles['LLM_API_Translator']['ollama model preferences'],
            preferences,
        )


if __name__ == '__main__':
    unittest.main()
