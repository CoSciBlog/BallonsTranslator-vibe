import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ballontranslator.glossary import (
    GlossaryCandidate,
    GlossaryCategory,
    GlossaryOrigin,
    GlossaryService,
    GlossaryStatus,
    RuleBasedGlossaryExtractor,
    check_translation_consistency,
    extract_and_store_candidates,
    parse_llm_candidates,
    project_prompt_entries,
    select_relevant_entries,
    term_occurs,
)
from ballontranslator.modules.context.translation_context import RequestContext
from ballontranslator.modules.translators.base import TransSource
from ballontranslator.modules.translators.trans_llm import LLMTranslator
from ballontranslator.modules.translators.llm_translation_contract import (
    TranslationPromptSpec,
    assemble_translation_request,
)
from ballontranslator.utils.config import ModuleConfig, pcfg
from ballontranslator.utils.llm_profiles import default_profile
from ballontranslator.utils.textblock import TextBlock


class GlossaryPhase2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.service = GlossaryService.for_project(Path(self.temp_dir.name))
        self.addCleanup(self.service.close)
        self._settings = {
            name: getattr(pcfg.module, name)
            for name in (
                'project_glossary_enabled',
                'project_glossary_auto_extract',
                'project_glossary_postcheck',
            )
        }
        self.addCleanup(self._restore_settings)

    def _restore_settings(self) -> None:
        for name, value in self._settings.items():
            setattr(pcfg.module, name, value)

    def _entry(self, original='Sakura', translation='Cherry', **values):
        values.setdefault('status', GlossaryStatus.CONFIRMED.value)
        return self.service.create_entry(
            original=original,
            translation=translation,
            **values,
        )

    def test_unicode_matching_uses_boundaries_and_cjk_substrings(self) -> None:
        self.assertTrue(term_occurs('Sakura arrives', 'sakura'))
        self.assertFalse(term_occurs('Sakurako arrives', 'Sakura'))
        self.assertTrue(term_occurs('勇者様が来た', '勇者'))
        self.assertTrue(term_occurs('김민수님', '김민수'))

    def test_invalid_optional_settings_fall_back_independently(self) -> None:
        config = ModuleConfig(
            project_glossary_enabled='yes',
            project_glossary_auto_extract=1,
            project_glossary_postcheck=None,
            project_glossary_max_prompt_entries=0,
            project_glossary_prompt_token_budget=True,
        )
        self.assertTrue(config.project_glossary_enabled)
        self.assertFalse(config.project_glossary_auto_extract)
        self.assertFalse(config.project_glossary_postcheck)
        self.assertEqual(config.project_glossary_max_prompt_entries, 32)
        self.assertEqual(config.project_glossary_prompt_token_budget, 1200)

    def test_phase3_settings_are_sanitized_independently(self) -> None:
        config = ModuleConfig(
            project_glossary_auto_create='yes',
            project_glossary_detection_categories=['Character', 'invalid', 4],
            project_glossary_reference_paths='reference.json',
            project_glossary_series_enabled=1,
            project_glossary_series_path=4,
            project_glossary_confirmation_mode='sometimes',
        )
        self.assertTrue(config.project_glossary_auto_create)
        self.assertEqual(config.project_glossary_detection_categories, ['Character'])
        self.assertEqual(config.project_glossary_reference_paths, [])
        self.assertFalse(config.project_glossary_series_enabled)
        self.assertEqual(config.project_glossary_series_path, '')
        self.assertEqual(config.project_glossary_confirmation_mode, 'manual')

    def test_alias_selects_confirmed_entry_and_preserves_metadata(self) -> None:
        entry = self._entry(
            original='Sakura Haruno',
            aliases=['Sakura'],
            category=GlossaryCategory.CHARACTER.value,
            source_language='English',
            target_language='Deutsch',
        )
        selected = select_relevant_entries(
            self.service.entries,
            ['Sakura arrives.'],
            source_language='English',
            target_language='Deutsch',
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].source, 'Sakura')
        self.assertEqual(selected[0].entry_id, entry.id)

    def test_suggestions_unknown_languages_and_unrelated_terms_are_not_sent(self) -> None:
        self.service.create_entry(original='Draft', translation='Entwurf')
        self._entry(
            original='Hero',
            translation='Held',
            source_language='English',
            target_language='Deutsch',
        )
        self._entry(original='Mage', translation='Magier')
        selected = select_relevant_entries(
            self.service.entries,
            ['Hero appears'],
            source_language='English',
            target_language='Français',
        )
        self.assertEqual(selected, ())

    def test_count_and_token_budgets_limit_prompt_entries(self) -> None:
        self._entry(original='Hero', translation='Held')
        self._entry(original='Mage', translation='Magier')
        by_count = select_relevant_entries(
            self.service.entries,
            ['Hero and Mage'],
            max_entries=1,
            token_budget=10000,
        )
        by_tokens = select_relevant_entries(
            self.service.entries,
            ['Hero and Mage'],
            max_entries=10,
            token_budget=1,
        )
        self.assertEqual([entry.source for entry in by_count], ['Hero'])
        self.assertEqual(by_tokens, ())

    def test_rule_extractor_rejects_dialogue_and_finds_names_and_titles(self) -> None:
        extractor = RuleBasedGlossaryExtractor()
        candidates = extractor.extract(
            ['Sakura Haruno', 'Hello there, how are you?', 'Captain Nemo arrived.'],
            ['Sakura Haruno', 'Hallo, wie geht es dir?', 'Kapitän Nemo kam.'],
        )
        terms = {candidate.original for candidate in candidates}
        self.assertIn('Sakura Haruno', terms)
        self.assertIn('Captain Nemo', terms)
        self.assertNotIn('Hello there', terms)

    def test_rule_extractor_classifies_places_organizations_abilities_and_items(self) -> None:
        candidates = RuleBasedGlossaryExtractor().extract([
            'Silver City', 'Moon Guild', 'Dragon Strike', 'Sun Blade', '勇者さん',
        ])
        categories = {
            candidate.original: candidate.category for candidate in candidates
        }
        self.assertEqual(categories['Silver City'], GlossaryCategory.PLACE)
        self.assertEqual(categories['Moon Guild'], GlossaryCategory.ORGANIZATION)
        self.assertEqual(categories['Dragon Strike'], GlossaryCategory.ABILITY)
        self.assertEqual(categories['Sun Blade'], GlossaryCategory.ITEM)
        self.assertEqual(categories['勇者さん'], GlossaryCategory.HONORIFIC)

    def test_mock_llm_candidates_are_validated_and_marked_as_llm(self) -> None:
        response = json.dumps({'candidates': [{
            'original': '黒炎',
            'translation': 'Black Flame',
            'category': 'Ability',
            'aliases': ['ブラックフレイム'],
            'confidence': 0.91,
        }]})
        candidate = parse_llm_candidates(response)[0]
        self.assertEqual(candidate.origin, GlossaryOrigin.LLM)
        self.assertEqual(candidate.category, GlossaryCategory.ABILITY)
        self.assertEqual(candidate.aliases, ('ブラックフレイム',))

    def test_candidates_merge_once_across_consecutive_pages(self) -> None:
        extractor = RuleBasedGlossaryExtractor()
        first = extract_and_store_candidates(
            self.service, ['Sakura'], ['Sakura'], extractor=extractor,
        )
        second = extract_and_store_candidates(
            self.service, ['Sakura'], ['Sakura'], extractor=extractor,
        )
        self.assertEqual(first.added, 1)
        self.assertEqual(second.duplicates, 1)
        self.assertEqual(len(self.service.entries), 1)
        self.assertEqual(self.service.entries[0].status, GlossaryStatus.SUGGESTION)
        self.assertEqual(self.service.entries[0].origin, GlossaryOrigin.OCR)
        self.assertIsNotNone(self.service.entries[0].confidence)

    def test_confirmed_protected_and_rejected_entries_are_not_overwritten(self) -> None:
        confirmed = self._entry(original='Hero', translation='Held')
        protected = self.service.create_entry(
            original='Mage', translation='', protected=True,
        )
        rejected = self.service.create_entry(
            original='Goblin', status=GlossaryStatus.REJECTED.value,
        )
        result = self.service.merge_automatic_candidates([
            {'original': 'Hero', 'translation': 'Champion', 'origin': 'LLM'},
            {'original': 'Mage', 'translation': 'Magier', 'origin': 'LLM'},
            {'original': 'Goblin', 'translation': 'Kobold', 'origin': 'LLM'},
        ])
        self.assertEqual(result.conflicts, 1)
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(result.suppressed, 1)
        self.assertEqual(self.service.get_entry(confirmed.id).translation, 'Held')
        self.assertEqual(self.service.get_entry(protected.id).translation, '')
        self.assertEqual(self.service.get_entry(rejected.id).status, GlossaryStatus.REJECTED)

    def test_alias_duplicate_is_not_recreated(self) -> None:
        self._entry(original='Sakura Haruno', aliases=['Sakura'])
        result = self.service.merge_automatic_candidates([
            {'original': 'Sakura', 'translation': 'Other', 'origin': 'LLM'},
        ])
        self.assertEqual(result.conflicts, 1)
        self.assertEqual(len(self.service.entries), 1)

    def test_conflicting_unconfirmed_translations_are_left_for_review(self) -> None:
        entry = self.service.create_entry(
            original='Sakura', translation='Kirschblüte', origin='OCR',
        )
        result = self.service.merge_automatic_candidates([
            {'original': 'Sakura', 'translation': 'Kirsche', 'origin': 'LLM'},
        ])
        self.assertEqual(result.conflicts, 1)
        self.assertEqual(
            self.service.get_entry(entry.id).translation,
            'Kirschblüte',
        )

    def test_candidate_aliases_cannot_bridge_two_existing_entries(self) -> None:
        self.service.create_entry(original='Hero', aliases=['Brave'])
        self.service.create_entry(original='Mage', aliases=['Wizard'])
        result = self.service.merge_automatic_candidates([{
            'original': 'Brave',
            'aliases': ['Wizard'],
            'origin': 'LLM',
        }])
        self.assertEqual(result.conflicts, 1)
        self.assertEqual(len(self.service.entries), 2)

    def test_parallel_candidate_merges_do_not_create_duplicates(self) -> None:
        barrier = threading.Barrier(3)
        results = []

        def merge() -> None:
            barrier.wait()
            results.append(self.service.merge_automatic_candidates([
                {'original': 'Sakura', 'translation': '', 'origin': 'OCR'},
            ]))

        threads = [threading.Thread(target=merge) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(len(self.service.entries), 1)
        self.assertEqual(sum(result.added for result in results), 1)

    def test_project_entries_are_injected_into_existing_prompt_contract(self) -> None:
        self._entry(original='Sakura', translation='桜')
        glossary = project_prompt_entries(self.service, ['Sakura appears'])
        context = RequestContext(history=(), glossary=glossary, glossary_mode='matching')
        messages, _ = assemble_translation_request(
            ('Sakura appears',),
            prompt_spec=TranslationPromptSpec('English', 'Japanese', 'system', False),
            request_context=context,
        )
        self.assertIn('confirmed project entry', messages[-1]['content'])
        self.assertIn('"translation":"桜"', messages[-1]['content'])

    def test_llm_translator_snapshots_project_glossary_without_extra_request(self) -> None:
        self._entry(original='Sakura', translation='桜')
        translator = LLMTranslator('English', '日本語')
        project = SimpleNamespace(glossary_service=self.service, pages={})
        profile = default_profile('OpenAI')
        profile.model = 'test-model'
        profile.model_options = ['test-model']
        with (
            mock.patch.object(
                LLMTranslator,
                'profile',
                new_callable=mock.PropertyMock,
                return_value=profile,
            ),
            mock.patch.object(translator, 'all_model_loaded', return_value=True),
            mock.patch.object(translator, '_translate', return_value=['桜']) as request,
        ):
            result = translator.translate(['Sakura'], project=project)
        context = request.call_args.kwargs['request_context']
        self.assertEqual(result, ['桜'])
        self.assertEqual(context.glossary[0].source, 'Sakura')
        self.assertEqual(request.call_count, 1)

    def test_llm_profile_can_disable_all_glossary_prompt_context(self) -> None:
        self._entry(original='Sakura', translation='桜')
        pcfg.module.project_glossary_enabled = True
        translator = LLMTranslator('English', '日本語')
        project = SimpleNamespace(glossary_service=self.service, pages={})
        profile = default_profile('OpenAI')
        profile.model = 'test-model'
        profile.model_options = ['test-model']
        profile.use_glossary = False
        with (
            mock.patch.object(
                LLMTranslator,
                'profile',
                new_callable=mock.PropertyMock,
                return_value=profile,
            ),
            mock.patch.object(pcfg.module, 'llm_glossary_path', 'unused.json'),
            mock.patch.object(translator, 'all_model_loaded', return_value=True),
            mock.patch.object(translator, '_translate', return_value=['桜']) as request,
        ):
            result = translator.translate(['Sakura'], project=project)

        self.assertEqual(result, ['桜'])
        self.assertIsNone(request.call_args.kwargs['request_context'])

    def test_postcheck_reports_but_does_not_replace_translation(self) -> None:
        entry = self._entry(original='Sakura', translation='桜')
        selected = select_relevant_entries(self.service.entries, ['Sakura appears'])
        issues = check_translation_consistency(
            selected, ['Sakura appears'], ['A girl appears'],
        )
        self.assertEqual(issues[0].entry_id, entry.id)

    def test_disabled_and_missing_glossary_keep_translation_path_unchanged(self) -> None:
        pcfg.module.project_glossary_enabled = False
        pcfg.module.project_glossary_auto_extract = True
        translator = TransSource('日本語', 'English')
        blocks = [TextBlock(text=['Sakura'])]
        project = SimpleNamespace(glossary_service=self.service)
        translator.translate_textblk_lst(blocks, project=project, page_key='001.png')
        self.assertEqual(blocks[0].translation, 'Sakura')
        self.assertEqual(self.service.entries, ())
        self.assertEqual(project_prompt_entries(None, ['Sakura']), ())

    def test_extractor_failure_does_not_lose_completed_translation(self) -> None:
        pcfg.module.project_glossary_enabled = True
        pcfg.module.project_glossary_auto_extract = True
        translator = TransSource('日本語', 'English')
        blocks = [TextBlock(text=['Sakura'])]
        project = SimpleNamespace(glossary_service=self.service)
        with mock.patch(
            'ballontranslator.modules.translators.base.extract_and_store_candidates',
            side_effect=RuntimeError('cancelled extractor'),
        ):
            translator.translate_textblk_lst(
                blocks, project=project, page_key='001.png'
            )
        self.assertEqual(blocks[0].translation, 'Sakura')
        self.assertEqual(self.service.entries, ())

    def test_translation_failure_does_not_store_candidates(self) -> None:
        pcfg.module.project_glossary_enabled = True
        pcfg.module.project_glossary_auto_extract = True
        translator = TransSource('日本語', 'English')
        blocks = [TextBlock(text=['Sakura'])]
        project = SimpleNamespace(glossary_service=self.service)
        with mock.patch.object(
            translator,
            'translate',
            side_effect=RuntimeError('provider stopped'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'provider stopped'):
                translator.translate_textblk_lst(
                    blocks, project=project, page_key='001.png'
                )
        self.assertEqual(self.service.entries, ())


if __name__ == '__main__':
    unittest.main()
