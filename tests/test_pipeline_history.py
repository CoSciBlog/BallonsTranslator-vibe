import unittest
from tempfile import TemporaryDirectory

from ui.pipeline_history_widget import PipelineHistoryWindow
from utils.proj_imgtrans import ProjImgTrans


class PipelineHistoryRowsTest(unittest.TestCase):
    def test_new_history_file_uses_schema_three(self):
        with TemporaryDirectory() as directory:
            project = ProjImgTrans()
            project.directory = directory

            project.append_pipeline_history({'pipeline': 'test'})

            history = project.load_pipeline_history()
            self.assertEqual(history['schema_version'], 3)
            self.assertEqual(history['entries'][0]['pipeline'], 'test')

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
                'duration_seconds': 12.345,
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
        self.assertEqual(rows[1][4], '12.3s')
        self.assertEqual(rows[1][7:], ['gemma-4-12b', 'Ollama', 'Yes'])

    def test_legacy_step_without_duration_keeps_duration_cell_blank(self):
        entry = {
            'duration_seconds': 20,
            'stages': {'detect': True},
            'modules': {'textdetector': {'name': 'ComicTextDetector'}},
        }

        rows = PipelineHistoryWindow._entry_rows(entry)

        self.assertEqual(rows[0][4], '20.0s')
        self.assertEqual(rows[1][4], '')

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
