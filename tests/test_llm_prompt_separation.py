import os.path as osp
import sys
import unittest

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from modules.translators.trans_llm_api import (
    GlossaryResponse,
    LLM_API_Translator,
    TranslationElement,
    TranslationResponse,
)


class PromptFakeTranslator(LLM_API_Translator):
    def __init__(self):
        self.lang_source = "Deutsch"
        self.lang_target = "English"
        self.lang_map = {"Deutsch": "German", "English": "English"}

    @property
    def reflection_prompt(self):
        return "Review the draft translation."

    @property
    def glossary_text(self):
        return "Quelle => Source [term]"

    @property
    def glossary_prompt(self):
        return "Use glossary entries as terminology guidance only."

    @property
    def use_glossary_enabled(self):
        return True

    @property
    def glossary_max_entries(self):
        return 200

    def _enabled_auto_glossary_categories(self):
        return {"term": "domain terms"}


class LLMPromptSeparationTest(unittest.TestCase):
    def test_reflection_prompt_uses_translation_response_schema(self):
        translator = PromptFakeTranslator()
        response = TranslationResponse(
            translations=[TranslationElement(id=1, translation="Draft")]
        )

        prompt = translator._build_reflection_prompt("INPUT", response)

        self.assertIn("ORIGINAL TRANSLATION TASK", prompt)
        self.assertIn('"translations"', prompt)
        self.assertIn('"translation"', prompt)
        self.assertNotIn("GlossaryResponse", prompt)

    def test_glossary_build_prompt_uses_glossary_response_schema(self):
        translator = PromptFakeTranslator()

        prompt = translator._build_glossary_extraction_prompt(["Quelle"], ["Source"], "English")

        self.assertIn("GlossaryResponse", prompt)
        self.assertIn('"entries"', prompt)
        self.assertIn('"source"', prompt)
        self.assertIn('"target"', prompt)
        self.assertNotIn('"translations"', prompt)

    def test_glossary_usage_is_guidance_only(self):
        translator = PromptFakeTranslator()

        prompt = translator._glossary_prompt_section()

        self.assertIn("GLOSSARY", prompt)
        self.assertIn("terminology guidance only", prompt)
        self.assertNotIn("Extract a reusable translation glossary", prompt)

    def test_config_models_still_validate(self):
        TranslationResponse.model_validate(
            {"translations": [{"id": 1, "translation": "A"}]}
        )
        GlossaryResponse.model_validate(
            {"entries": [{"source": "A", "target": "B", "category": "term", "note": ""}]}
        )


if __name__ == "__main__":
    unittest.main()
