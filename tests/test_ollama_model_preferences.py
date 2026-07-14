import unittest

from utils.ollama import (
    OLLAMA_DEFAULT_ENDPOINT,
    ollama_model_matches_filters,
    ollama_model_matches_query,
    ollama_model_parameter_size,
    ollama_model_sort_value,
    ollama_parameter_size_sort_key,
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

    def test_parameter_size_is_read_from_name_or_declared_metadata(self):
        self.assertEqual(ollama_model_parameter_size('gemma4:12b'), '12B')
        self.assertEqual(ollama_model_parameter_size('qwen3:30b-a3b'), '30B')
        self.assertEqual(ollama_model_parameter_size('embedding:335m'), '335M')
        self.assertEqual(ollama_model_parameter_size('custom:latest', '27.0B'), '27B')
        self.assertEqual(
            sorted(['27B', '335M', '1.5B', '12B'], key=ollama_parameter_size_sort_key),
            ['335M', '1.5B', '12B', '27B'],
        )

    def test_model_filters_can_be_combined(self):
        values = dict(
            model_name='gemma4:12b-thinking',
            query='gemma',
            model_parameter_size='12B',
            parameter_size_filter='12b',
            reasoning_status='yes',
            reasoning_filter='yes',
            rating=4,
            minimum_rating=4,
        )
        self.assertTrue(ollama_model_matches_filters(**values))
        self.assertFalse(ollama_model_matches_filters(**{**values, 'parameter_size_filter': '27B'}))
        self.assertFalse(ollama_model_matches_filters(**{**values, 'reasoning_filter': 'no'}))
        self.assertFalse(ollama_model_matches_filters(**{**values, 'minimum_rating': 5}))

    def test_sort_values_support_model_reasoning_and_rating_columns(self):
        self.assertLess(
            ollama_model_sort_value('model', model_name='Gemma:12b'),
            ollama_model_sort_value('model', model_name='qwen:12b'),
        )
        self.assertEqual(
            sorted(['yes', 'unknown', 'no'], key=lambda value: ollama_model_sort_value(
                'reasoning', reasoning_status=value
            )),
            ['no', 'unknown', 'yes'],
        )
        self.assertLess(
            ollama_model_sort_value('rating', rating=2),
            ollama_model_sort_value('rating', rating=5),
        )

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
