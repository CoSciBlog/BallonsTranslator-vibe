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
        self.logger = FakeLogger()

    @property
    def reflection_prompt(self):
        return "Review the draft translation."

    @property
    def glossary_text(self):
        return (
            "友利 => Tomori [character] # aliases: Tomoly; female character\n"
            "さん => Mr./Ms. [honorific] # use only when natural\n"
            "Quelle => Source [term]"
        )

    @property
    def glossary_prompt(self):
        return "Use glossary entries as terminology guidance only."

    @property
    def glossary_reference_text(self):
        return "港町 => Harbor City [place] # official translation"

    @property
    def glossary_reference_prompt(self):
        return "Prefer official reference spellings."

    @property
    def use_glossary_enabled(self):
        return True

    @property
    def glossary_max_entries(self):
        return 200

    def _enabled_auto_glossary_categories(self):
        return {"character": "character/person names"}


class FakeLogger:
    def __init__(self):
        self.infos = []

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        pass

    def debug(self, message):
        pass

    def error(self, message):
        pass


class LLMPromptSeparationTest(unittest.TestCase):
    def test_reflection_prompt_uses_translation_response_schema(self):
        translator = PromptFakeTranslator()
        response = TranslationResponse(
            translations=[TranslationElement(id=1, translation="Draft")]
        )

        prompt = translator._build_reflection_prompt("INPUT", response)

        self.assertIn("ORIGINAL TRANSLATION TASK", prompt)
        self.assertIn("Check pronoun consistency", prompt)
        self.assertIn("male characters are not translated with feminine pronouns", prompt)
        self.assertIn("female or girl characters are not translated with masculine pronouns", prompt)
        self.assertIn("speaker and addressee", prompt)
        self.assertIn("Do not change I/me/my into we/us/our", prompt)
        self.assertIn("Do not change you into they/he/she", prompt)
        self.assertIn("address forms and honorifics", prompt)
        self.assertIn("same IDs", prompt)
        self.assertIn("same item count", prompt)
        self.assertIn("RELEVANT GLOSSARY FOR REVIEW", prompt)
        self.assertIn("友利 -> Tomori", prompt)
        self.assertIn("aliases: Tomoly", prompt)
        self.assertIn('"translations"', prompt)
        self.assertIn('"translation"', prompt)
        self.assertIn("TranslationResponse schema", prompt)
        self.assertNotIn("category labels, aliases, notes, confidence", prompt.split("DRAFT TRANSLATION JSON:")[-1])
        self.assertNotIn("GlossaryResponse", prompt)

    def test_glossary_build_prompt_uses_glossary_response_schema(self):
        translator = PromptFakeTranslator()

        prompt = translator._build_glossary_extraction_prompt(["Quelle"], ["Source"], "English")

        self.assertIn("GlossaryResponse", prompt)
        self.assertIn('"entries"', prompt)
        self.assertIn('"source"', prompt)
        self.assertIn('"target"', prompt)
        self.assertIn('"aliases"', prompt)
        self.assertIn('"notes"', prompt)
        self.assertIn('"confidence"', prompt)
        self.assertIn("Never return {}", prompt)
        self.assertIn('{"entries":[]}', prompt)
        self.assertIn('category "character"', prompt)
        self.assertIn("draft_translation", prompt)
        self.assertIn("official/reference translation", prompt)
        self.assertIn("REFERENCE GLOSSARY", prompt)
        self.assertIn("Harbor City", prompt)
        self.assertNotIn('"translations"', prompt)

    def test_glossary_usage_is_guidance_only(self):
        translator = PromptFakeTranslator()

        prompt = translator._glossary_prompt_section()

        self.assertIn("GLOSSARY", prompt)
        self.assertIn("terminology guidance only", prompt)
        self.assertIn("never copy that metadata into the translation", prompt)
        self.assertNotIn("Extract a reusable translation glossary", prompt)

    def test_review_glossary_context_filters_relevant_categories(self):
        translator = PromptFakeTranslator()

        prompt = translator._review_glossary_prompt_section()

        self.assertIn("[character] 友利 -> Tomori", prompt)
        self.assertIn("[honorific] さん -> Mr./Ms.", prompt)
        self.assertNotIn("[term] Quelle", prompt)
        self.assertIn("Review glossary guidance enabled", translator.logger.infos[0])

    def test_config_models_still_validate(self):
        TranslationResponse.model_validate(
            {"translations": [{"id": 1, "translation": "A"}]}
        )
        GlossaryResponse.model_validate(
            {"entries": [{"source": "A", "target": "B", "category": "character", "aliases": [], "note": ""}]}
        )


if __name__ == "__main__":
    unittest.main()
