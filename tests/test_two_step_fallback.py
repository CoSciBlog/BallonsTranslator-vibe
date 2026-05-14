import os.path as osp
import sys
import unittest

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from modules.translators.trans_llm_api import TranslationElement, TranslationResponse
from modules.translators.trans_two_step import TwoStepTranslator


class FakeLogger:
    def __init__(self):
        self.warnings = []
        self.debugs = []

    def warning(self, message):
        self.warnings.append(message)

    def debug(self, message):
        self.debugs.append(message)

    def info(self, message):
        pass

    def error(self, message):
        raise AssertionError(f"unexpected error log: {message}")


class FakeTwoStepTranslator(TwoStepTranslator):
    def __init__(self, drafts, response=None, error=None):
        self._drafts = drafts
        self._response = response
        self._error = error
        self.glossary_updates = []
        self.logger = FakeLogger()
        self.lang_target = "English"
        self.lang_source = "Deutsch"
        self.lang_map = {"English": "English", "Deutsch": "German"}
        self.last_refinement_used_draft_fallback = False

    @property
    def fallback_to_first_step(self):
        return True

    def _first_step_translate(self, src_list):
        return list(self._drafts)

    def _translation_context_prompt_section(self):
        return ""

    def _glossary_prompt_section(self):
        return ""

    def _request_translation(self, prompt, is_reflection=False):
        if self._error:
            raise self._error
        return self._response

    def _update_glossary_from_batch(self, src_list, translations, to_lang):
        self.glossary_updates.append((list(src_list), list(translations), to_lang))

    def _refine_translations_with_glossary(self, src_list, translations, to_lang):
        return translations


class TwoStepFallbackTest(unittest.TestCase):
    def test_refined_translations_are_used_when_valid(self):
        response = TranslationResponse(
            translations=[TranslationElement(id=1, translation="Refined")]
        )
        translator = FakeTwoStepTranslator(["Draft"], response=response)

        result = translator._translate(["Quelle"])

        self.assertEqual(result, ["Refined"])
        self.assertFalse(translator.last_refinement_used_draft_fallback)

    def test_empty_llm_response_falls_back_to_draft(self):
        response = TranslationResponse(translations=[])
        translator = FakeTwoStepTranslator(["Draft"], response=response)

        result = translator._translate(["Quelle"])

        self.assertEqual(result, ["Draft"])
        self.assertTrue(translator.last_refinement_used_draft_fallback)
        self.assertIn(
            "LLM refinement failed; using first-step draft translations for this page/block.",
            translator.logger.warnings,
        )

    def test_llm_exception_falls_back_to_draft(self):
        translator = FakeTwoStepTranslator(["Draft"], error=ValueError("bad json"))

        result = translator._translate(["Quelle"])

        self.assertEqual(result, ["Draft"])
        self.assertTrue(translator.last_refinement_used_draft_fallback)
        self.assertEqual(translator.glossary_updates, [(["Quelle"], ["Draft"], "English")])

    def test_missing_draft_keeps_source_text(self):
        translator = FakeTwoStepTranslator([""], error=ValueError("bad json"))

        result = translator._translate(["Quelle"])

        self.assertEqual(result, ["Quelle"])
        self.assertTrue(translator.last_refinement_used_draft_fallback)
        self.assertIn(
            "LLM refinement failed and no first-step draft translations were available.",
            translator.logger.warnings,
        )
        self.assertEqual(translator.glossary_updates, [(["Quelle"], ["Quelle"], "English")])


if __name__ == "__main__":
    unittest.main()
