import unittest

from ui.pipeline_history_widget import PipelineHistoryWindow


class PipelineHistoryRowsTest(unittest.TestCase):
    def test_legacy_entry_is_expanded_into_enabled_step_rows(self):
        entry = {
            'started_at': '2026-07-13T19:54:05Z',
            'pipeline': 'image_translation_pipeline',
            'status': 'completed',
            'duration_seconds': 73.7,
            'page_count': 2,
            'stages': {
                'detect': True,
                'ocr': True,
                'translate': True,
                'inpaint': False,
            },
            'modules': {
                'textdetector': {'name': 'ComicTextDetector'},
                'ocr': {'name': 'manga_ocr'},
                'translator': {
                    'name': 'LLM_API_Translator',
                    'provider': 'Ollama',
                    'model': 'qwen3.5:9b',
                    'reasoning': False,
                },
                'inpainter': {'name': 'lama_large_512px'},
            },
        }

        rows = PipelineHistoryWindow._entry_rows(entry)

        self.assertEqual([row[2] for row in rows], [
            'Pipeline', 'Text Detection', 'OCR', 'Translate'
        ])
        self.assertEqual(rows[-1][6:], [
            'LLM_API_Translator', 'qwen3.5:9b', 'Ollama', 'No'
        ])

    def test_schema_two_steps_use_saved_values_and_reasoning(self):
        entry = {
            'pipeline': 'translation_only_pipeline',
            'status': 'completed',
            'steps': [{
                'step': 'translate',
                'label': 'Translate',
                'enabled': True,
                'status': 'completed',
                'module': {
                    'name': 'LLM_API_Translator',
                    'provider': 'Ollama',
                    'effective_model': 'gemma-4-12b',
                    'reasoning': True,
                },
            }],
        }

        rows = PipelineHistoryWindow._entry_rows(entry)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][2], 'Translate')
        self.assertEqual(rows[1][7:], ['gemma-4-12b', 'Ollama', 'Yes'])

    def test_reasoning_is_blank_for_non_ollama_provider(self):
        entry = {
            'steps': [{
                'step': 'translate',
                'enabled': True,
                'module': {'provider': 'OpenAI', 'reasoning': True},
            }],
        }

        self.assertEqual(PipelineHistoryWindow._entry_rows(entry)[1][-1], '')


if __name__ == '__main__':
    unittest.main()
