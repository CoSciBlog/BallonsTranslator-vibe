import os.path as osp
import sys
import unittest

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from modules.translators.trans_llm_api import TranslationElement, TranslationResponse
from modules.translators.trans_two_step import TwoStepTranslator
from utils.textblock import TextBlock


class FakeLogger:
    def __init__(self):
        self.warnings = []
        self.debugs = []
        self.infos = []

    def warning(self, message):
        self.warnings.append(message)

    def debug(self, message):
        self.debugs.append(message)

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        raise AssertionError(f"unexpected error log: {message}")


class FakeTwoStepTranslator(TwoStepTranslator):
    def __init__(self, drafts, responses=None, errors=None, fallback=True, chunk_size=8, shortening="Off"):
        self._drafts = drafts
        self._responses = list(responses or [])
        self._errors = list(errors or [])
        self._fallback = fallback
        self._chunk_size = chunk_size
        self._shortening = shortening
        self.requests = []
        self.glossary_updates = []
        self.logger = FakeLogger()
        self.lang_target = "English"
        self.lang_source = "Deutsch"
        self.lang_map = {"English": "English", "Deutsch": "German"}
        self.last_refinement_used_draft_fallback = False
        self._preprocess_hooks = {}
        self._postprocess_hooks = {}

    @property
    def fallback_to_first_step(self):
        return self._fallback

    @property
    def max_tokens(self):
        return 4096

    @property
    def max_refinement_items_per_request(self):
        return self._chunk_size

    @property
    def bubble_text_shortening(self):
        return self._shortening

    @property
    def long_bubble_character_target(self):
        return 60

    @property
    def extreme_bubble_character_target(self):
        return 100

    def _first_step_translate(self, src_list):
        return list(self._drafts)

    def _translation_context_prompt_section(self):
        return ""

    def _glossary_prompt_section(self):
        return ""

    def _review_glossary_prompt_section(self):
        return ""

    def _request_translation(self, prompt, is_reflection=False, **kwargs):
        self.requests.append({"prompt": prompt, "is_reflection": is_reflection, **kwargs})
        if self._errors:
            error = self._errors.pop(0)
            if error is not None:
                raise error
        if self._responses:
            return self._responses.pop(0)
        return None

    def _update_glossary_from_batch(self, src_list, translations, to_lang):
        self.glossary_updates.append((list(src_list), list(translations), to_lang))

    def _refine_translations_with_glossary(self, src_list, translations, to_lang):
        return translations


class TwoStepFallbackTest(unittest.TestCase):
    def test_refined_translations_are_used_when_valid(self):
        response = TranslationResponse(
            translations=[TranslationElement(id=1, translation="Refined")]
        )
        translator = FakeTwoStepTranslator(["Draft"], responses=[response])

        result = translator._translate(["Quelle"])

        self.assertEqual(result, ["Refined"])
        self.assertFalse(translator.last_refinement_used_draft_fallback)
        self.assertEqual(len(translator.requests), 1)
        self.assertFalse(translator.requests[0]["is_reflection"])

    def test_llm_can_copy_draft_without_marking_draft_fallback(self):
        response = TranslationResponse(
            translations=[TranslationElement(id=1, translation="Draft")]
        )
        translator = FakeTwoStepTranslator(["Draft"], responses=[response])

        result = translator._translate(["Quelle"])

        self.assertEqual(result, ["Draft"])
        self.assertFalse(translator.last_refinement_used_draft_fallback)
        self.assertFalse(
            any("draft fallback used" in warning for warning in translator.logger.warnings)
        )

    def test_empty_llm_response_retries_before_draft_fallback(self):
        empty = TranslationResponse(translations=[])
        retry = TranslationResponse(
            translations=[TranslationElement(id=1, translation="Retry")]
        )
        translator = FakeTwoStepTranslator(["Draft"], responses=[empty, retry])

        result = translator._translate(["Quelle"])

        self.assertEqual(result, ["Retry"])
        self.assertFalse(translator.last_refinement_used_draft_fallback)
        self.assertEqual([request["purpose"] for request in translator.requests], ["normal_refinement", "strict_refinement_retry"])

    def test_llm_exception_falls_back_to_draft(self):
        empty = TranslationResponse(translations=[])
        translator = FakeTwoStepTranslator(
            ["Draft"],
            responses=[empty],
            errors=[ValueError("bad json"), None],
        )

        result = translator._translate(["Quelle"])

        self.assertEqual(result, ["Draft"])
        self.assertTrue(translator.last_refinement_used_draft_fallback)
        self.assertEqual(translator.glossary_updates, [(["Quelle"], ["Draft"], "English")])
        self.assertTrue(
            any("draft fallback used" in warning for warning in translator.logger.warnings)
        )

    def test_fallback_disabled_returns_empty_when_retry_fails(self):
        empty = TranslationResponse(translations=[])
        translator = FakeTwoStepTranslator(
            ["Draft"],
            responses=[empty, empty],
            fallback=False,
        )

        result = translator._translate(["Quelle"])

        self.assertEqual(result, [""])
        self.assertFalse(translator.last_refinement_used_draft_fallback)

    def test_missing_draft_keeps_source_text(self):
        empty = TranslationResponse(translations=[])
        translator = FakeTwoStepTranslator([""], responses=[empty, empty])

        result = translator._translate(["Quelle"])

        self.assertEqual(result, ["Quelle"])
        self.assertTrue(translator.last_refinement_used_draft_fallback)
        self.assertIn(
            "LLM refinement failed and no first-step draft translations were available.",
            translator.logger.warnings,
        )
        self.assertEqual(translator.glossary_updates, [(["Quelle"], ["Quelle"], "English")])

    def test_partial_response_triggers_retry(self):
        partial = TranslationResponse(
            translations=[TranslationElement(id=1, translation="One")]
        )
        retry = TranslationResponse(
            translations=[
                TranslationElement(id=1, translation="Retry One"),
                TranslationElement(id=2, translation="Retry Two"),
            ]
        )
        translator = FakeTwoStepTranslator(["Draft1", "Draft2"], responses=[partial, retry])

        result = translator._translate(["Quelle1", "Quelle2"])

        self.assertEqual(result, ["Retry One", "Retry Two"])
        self.assertEqual(len(translator.requests), 2)

    def test_wrong_ids_trigger_retry(self):
        wrong = TranslationResponse(
            translations=[TranslationElement(id=99, translation="Wrong")]
        )
        retry = TranslationResponse(
            translations=[TranslationElement(id=1, translation="Retry")]
        )
        translator = FakeTwoStepTranslator(["Draft"], responses=[wrong, retry])

        result = translator._translate(["Quelle"])

        self.assertEqual(result, ["Retry"])
        self.assertTrue(any("extra_ids=[99]" in warning for warning in translator.logger.warnings))

    def test_merge_is_id_based_and_not_positional(self):
        normal = TranslationResponse(
            translations=[
                TranslationElement(id=2, translation="Two"),
                TranslationElement(id=1, translation="One"),
            ]
        )
        translator = FakeTwoStepTranslator(["Draft1", "Draft2"])
        expected = translator._expected_refinement_items(["Quelle1", "Quelle2"], ["Draft1", "Draft2"])

        result = translator.merge_refinement_with_drafts(expected, normal, None)

        self.assertEqual(result, ["One", "Two"])

    def test_retry_overrides_normal_and_extra_ids_are_ignored(self):
        normal = TranslationResponse(
            translations=[
                TranslationElement(id=1, translation="Normal One"),
                TranslationElement(id=2, translation="Normal Two"),
                TranslationElement(id=9, translation="Extra"),
            ]
        )
        retry = TranslationResponse(
            translations=[TranslationElement(id=2, translation="Retry Two")]
        )
        translator = FakeTwoStepTranslator(["Draft1", "Draft2"])
        expected = translator._expected_refinement_items(["Quelle1", "Quelle2"], ["Draft1", "Draft2"])

        result = translator.merge_refinement_with_drafts(expected, normal, retry)

        self.assertEqual(result, ["Normal One", "Retry Two"])
        self.assertIn("Extra refinement ids ignored: [9]", translator.logger.warnings)

    def test_partial_normal_and_retry_fall_back_by_id(self):
        normal = TranslationResponse(
            translations=[TranslationElement(id=1, translation="Normal One")]
        )
        retry = TranslationResponse(
            translations=[TranslationElement(id=2, translation="Retry Two")]
        )
        translator = FakeTwoStepTranslator(["Draft1", "Draft2", "Draft3"])
        expected = translator._expected_refinement_items(
            ["Quelle1", "Quelle2", "Quelle3"],
            ["Draft1", "Draft2", "Draft3"],
        )

        result = translator.merge_refinement_with_drafts(expected, normal, retry)

        self.assertEqual(result, ["Normal One", "Retry Two", "Draft3"])

    def test_chunking_tracks_expected_ids_and_retries_once_per_chunk(self):
        empty = TranslationResponse(translations=[])
        translator = FakeTwoStepTranslator(
            ["D1", "D2", "D3"],
            responses=[empty, empty, empty, empty],
            chunk_size=2,
        )

        result = translator._translate(["S1", "S2", "S3"])

        self.assertEqual(result, ["D1", "D2", "D3"])
        self.assertEqual(len(translator.requests), 4)
        self.assertEqual(translator.requests[0]["expected_ids"], [1, 2])
        self.assertEqual(translator.requests[2]["expected_ids"], [3])

    def test_prompt_separation(self):
        translator = FakeTwoStepTranslator(["Draft"])
        expected = translator._expected_refinement_items(["Quelle"], ["Draft"])
        normal_prompt = translator._assemble_refinement_prompt_from_items(expected, "English")
        retry_prompt = translator._assemble_strict_refinement_retry_prompt(expected, "English")

        self.assertIn('{ "translations": [ {"id": 1, "translation": "final improved translation"} ] }', normal_prompt)
        self.assertIn("Expected IDs: [1]", normal_prompt)
        self.assertIn("Never return {}", normal_prompt)
        self.assertIn("Required IDs", retry_prompt)
        self.assertIn("Check pronoun consistency", normal_prompt)
        self.assertIn("Do not change I/me/my into we/us/our", normal_prompt)
        self.assertIn("Do not change you into they/he/she", normal_prompt)
        self.assertIn("If unsure, copy the draft unchanged", retry_prompt)
        self.assertNotIn("ORIGINAL TRANSLATION TASK", retry_prompt)
        self.assertNotIn("GlossaryResponse", normal_prompt)
        self.assertIn('"source": "Quelle"', normal_prompt)
        self.assertIn('"draft_translation": "Draft"', normal_prompt)

    def test_optional_bubble_shortening_guidance_is_added_to_refinement_prompt(self):
        translator = FakeTwoStepTranslator(
            ["Draft"], shortening="Shorten long and extremely long translations"
        )
        expected = translator._expected_refinement_items(["Quelle"], ["Draft"])

        prompt = translator._assemble_refinement_prompt_from_items(expected, "English")

        self.assertIn("SPEECH-BUBBLE LENGTH GUIDANCE", prompt)
        self.assertIn("longer than about 60 characters", prompt)
        self.assertIn("longer than about 100 characters", prompt)

    def test_text_blocks_keep_machine_draft_and_llm_review_separately(self):
        response = TranslationResponse(
            translations=[TranslationElement(id=1, translation="LLM review")]
        )
        translator = FakeTwoStepTranslator(["Machine draft"], responses=[response])
        blocks = [TextBlock(text=["Quelle"])]

        translator.translate_textblk_lst(blocks)

        self.assertEqual(blocks[0].translation_draft, "Machine draft")
        self.assertEqual(blocks[0].translation_llm_review, "LLM review")
        self.assertEqual(blocks[0].translation, "LLM review")

    def test_machine_fallback_is_not_labelled_as_llm_review(self):
        empty = TranslationResponse(translations=[])
        translator = FakeTwoStepTranslator(["Machine draft"], responses=[empty, empty])
        blocks = [TextBlock(text=["Quelle"])]

        translator.translate_textblk_lst(blocks)

        self.assertEqual(blocks[0].translation, "Machine draft")
        self.assertEqual(blocks[0].translation_draft, "Machine draft")
        self.assertEqual(blocks[0].translation_llm_review, "")
        self.assertTrue(blocks[0].translation_draft_fallback)


if __name__ == "__main__":
    unittest.main()
