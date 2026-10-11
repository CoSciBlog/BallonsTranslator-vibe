import unittest
from copy import deepcopy
from unittest import mock

from ballontranslator.modules.translators.trans_google import TransGoogle
from ballontranslator.modules.translators.trans_llm import LLMTranslator
from ballontranslator.modules.translators.trans_two_step import (
    DEEPL_FREE_API_URL,
    TwoStepTranslator,
)
from ballontranslator.utils.config import pcfg
from ballontranslator.utils.llm_profiles import LLMProfile
from ballontranslator.utils.textblock import TextBlock


class TwoStepTranslatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ollama_profile = LLMProfile(
            id='ollama',
            name='Ollama',
            base_url='http://127.0.0.1:11434/v1',
            model='local-model',
            model_options=['local-model'],
            support_text=True,
        )
        self.profile_patch = mock.patch.object(
            pcfg.module, 'llm_profiles', [self.ollama_profile]
        )
        self.profile_id_patch = mock.patch.object(
            pcfg.module, 'translator_llm_id', self.ollama_profile.id
        )
        self.profile_patch.start()
        self.profile_id_patch.start()

    def tearDown(self) -> None:
        self.profile_id_patch.stop()
        self.profile_patch.stop()

    def _translator(self, **values) -> TwoStepTranslator:
        params = deepcopy(TwoStepTranslator.params)
        for key, value in values.items():
            params[key.replace('_', ' ')]['value'] = value
        return TwoStepTranslator('日本語', 'English', **params)

    def test_google_draft_is_refined_by_llm_translator(self) -> None:
        translator = self._translator()
        translator._first_step = mock.Mock(return_value=['Hello'])
        captured = {}

        def refine(_instance, text, **kwargs):
            captured['text'] = text
            captured['kwargs'] = kwargs
            return ['Hello there']

        with mock.patch.object(LLMTranslator, 'translate', autospec=True, side_effect=refine):
            result = translator.translate(
                ['こんにちは'], page_key='001.png', commit_history_window=True
            )

        self.assertEqual(result, ['Hello there'])
        self.assertEqual(
            captured['text'],
            ['{"source": "こんにちは", "draft_translation": "Hello"}'],
        )
        self.assertEqual(captured['kwargs']['page_key'], '001.png')
        self.assertTrue(captured['kwargs']['commit_history_window'])

    def test_refinement_failure_can_keep_machine_translation(self) -> None:
        translator = self._translator(fallback_to_first_step=True)
        translator._first_step = mock.Mock(return_value=['Draft'])
        with mock.patch.object(
            LLMTranslator, 'translate', side_effect=RuntimeError('offline')
        ):
            self.assertEqual(translator.translate(['原文']), ['Draft'])

    def test_project_stages_finish_drafts_before_ollama_refinement(self) -> None:
        translator = self._translator()
        translator._first_step = mock.Mock(return_value=['Machine draft'])
        block = TextBlock(text=['原文'])

        with (
            mock.patch.object(
                LLMTranslator,
                'translate',
                autospec=True,
                return_value=['Refined translation'],
            ) as llm_translate,
            mock.patch(
                'ballontranslator.modules.translators.trans_two_step.'
                'postprocess_translation_text',
                side_effect=lambda text, *_args, **_kwargs: text,
            ) as postprocess,
        ):
            translator.translate_first_step_textblk_lst(
                [block],
                page_key='001.png',
                full_page=True,
            )
            self.assertEqual(block.translation, 'Machine draft')
            llm_translate.assert_not_called()

            translator.refine_textblk_lst(
                [block],
                page_key='001.png',
                full_page=True,
            )

        self.assertEqual(block.translation, 'Refined translation')
        translator._first_step.assert_called_once_with(['原文'])
        llm_translate.assert_called_once()
        postprocess.assert_called_once()
        self.assertEqual(
            llm_translate.call_args.args[1],
            ['{"source": "原文", "draft_translation": "Machine draft"}'],
        )

    def test_deepl_free_uses_configured_endpoint_and_key(self) -> None:
        translator = self._translator(
            first_step_translator='DeepL Free', deepl_api_key='key'
        )
        response = mock.Mock()
        response.json.return_value = {'translations': [{'text': 'Hello'}]}
        with mock.patch(
            'ballontranslator.modules.translators.trans_two_step.requests.post',
            return_value=response,
        ) as request:
            result = translator._first_step(['こんにちは'])

        self.assertEqual(result, ['Hello'])
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], DEEPL_FREE_API_URL)
        self.assertIn(('auth_key', 'key'), request.call_args.kwargs['data'])

    def test_profile_requires_local_ollama(self) -> None:
        translator = self._translator()
        profile = LLMProfile(
            id='remote',
            name='Remote',
            base_url='https://api.example/v1',
            model='model',
            model_options=['model'],
            support_text=True,
        )
        with (
            mock.patch.object(pcfg.module, 'llm_profiles', [profile]),
            mock.patch.object(pcfg.module, 'translator_llm_id', profile.id),
        ):
            with self.assertRaisesRegex(RuntimeError, 'local Ollama'):
                _ = translator.profile

    def test_standalone_google_does_not_call_llm(self) -> None:
        translator = TransGoogle('日本語', 'English')
        translator.internal_google_translator.translate = mock.Mock(
            return_value={'translations': ['Hello']}
        )
        with mock.patch.object(LLMTranslator, 'translate') as llm_translate:
            result = translator.translate(['こんにちは'])

        self.assertEqual(result, ['Hello'])
        llm_translate.assert_not_called()

    def test_profile_google_first_pass_stages_draft_then_llm_refinement(self) -> None:
        self.ollama_profile.google_first_pass = True
        self.ollama_profile.google_fallback_to_draft = True
        translator = LLMTranslator(
            '日本語',
            'English',
            **deepcopy(LLMTranslator.params),
        )
        translator._google_first_step = mock.Mock(return_value=['Google draft'])
        block = TextBlock(text=['原文'])

        self.assertTrue(translator.staged_project_translation)
        translator.translate_first_step_textblk_lst(
            [block],
            page_key='001.png',
            full_page=True,
        )
        self.assertEqual(block.translation, 'Google draft')

        with (
            mock.patch.object(
                translator,
                'translate',
                return_value=['Natural refinement'],
            ) as llm_translate,
            mock.patch(
                'ballontranslator.modules.translators.trans_llm.'
                'postprocess_translation_text',
                side_effect=lambda text, *_args, **_kwargs: text,
            ),
        ):
            translator.refine_textblk_lst(
                [block],
                page_key='001.png',
                full_page=True,
            )

        self.assertEqual(block.translation, 'Natural refinement')
        self.assertEqual(
            llm_translate.call_args.args[0],
            ['{"source": "原文", "draft_translation": "Google draft"}'],
        )
        self.assertFalse(translator._google_refinement_active)


if __name__ == '__main__':
    unittest.main()
