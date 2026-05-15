import os.path as osp
import sys
import unittest

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from modules.translators.trans_llm_api import GlossaryResponse, LLM_API_Translator


class FakeLogger:
    def __init__(self):
        self.warnings = []
        self.infos = []

    def warning(self, message):
        self.warnings.append(message)

    def info(self, message):
        self.infos.append(message)


class GlossaryResponseNormalizationTest(unittest.TestCase):
    def validate(self, payload):
        normalized = LLM_API_Translator._normalize_glossary_response_data(payload)
        return GlossaryResponse.model_validate(normalized)

    def test_entries_shape_remains_valid(self):
        response = self.validate(
            {"entries": [{"source": "Tomori", "target": "Tomori", "category": "name"}]}
        )

        self.assertEqual(len(response.entries), 1)
        self.assertEqual(response.entries[0].target, "Tomori")
        self.assertEqual(response.entries[0].category, "character")

    def test_list_is_wrapped_as_entries(self):
        response = self.validate(
            [{"source": "Tomori", "target": "Tomori", "category": "name"}]
        )

        self.assertEqual(len(response.entries), 1)
        self.assertEqual(response.entries[0].source, "Tomori")

    def test_single_entry_dict_is_wrapped(self):
        response = self.validate(
            {"source": "Adam", "target": "Little Adam", "category": "name"}
        )

        self.assertEqual(len(response.entries), 1)
        self.assertEqual(response.entries[0].target, "Little Adam")
        self.assertEqual(response.entries[0].category, "character")

    def test_alternate_terms_key_is_wrapped(self):
        response = self.validate(
            {"terms": [{"source": "Eden", "target": "Garden of Eden", "category": "place"}]}
        )

        self.assertEqual(len(response.entries), 1)
        self.assertEqual(response.entries[0].category, "place")

    def test_empty_dict_returns_empty_entries_and_logs_warning(self):
        logger = FakeLogger()
        normalized = LLM_API_Translator._normalize_glossary_response_data({}, logger)
        response = GlossaryResponse.model_validate(normalized)

        self.assertEqual(response.entries, [])
        self.assertIn(
            "LLM returned empty glossary JSON object; no glossary entries were extracted.",
            logger.warnings,
        )

    def test_notes_and_alias_string_are_normalized(self):
        response = self.validate(
            {
                "entries": [
                    {
                        "source": "Tomori",
                        "target": "Tomori",
                        "category": "name",
                        "aliases": "Tomoly, Yuuri",
                        "notes": "female character",
                        "confidence": 0.75,
                    }
                ]
            }
        )

        entry = response.entries[0]
        self.assertEqual(entry.category, "character")
        self.assertEqual(entry.aliases, ["Tomoly", "Yuuri"])
        self.assertEqual(entry.note, "female character")
        self.assertEqual(entry.confidence, 0.75)


class GlossaryMergeTest(unittest.TestCase):
    def make_translator(self, glossary, enabled=None):
        class MergeFakeTranslator(LLM_API_Translator):
            def __init__(self):
                self._glossary = glossary
                self._enabled = enabled if enabled is not None else {"character": "names"}
                self.logger = FakeLogger()

            @property
            def glossary_text(self):
                return self._glossary

            @property
            def glossary_max_entries(self):
                return 200

            def _enabled_auto_glossary_categories(self):
                return dict(self._enabled)

            def set_param_value(self, param_key, param_value, convert_dtype=True):
                if param_key == "glossary":
                    self._glossary = param_value

        return MergeFakeTranslator()

    def test_character_names_are_saved_and_name_category_is_normalized(self):
        translator = self.make_translator("")

        saved = translator._save_glossary_entries(
            GlossaryResponse.model_validate(
                {
                    "entries": [
                        {
                            "source": "Tomori",
                            "target": "Tomori",
                            "category": "name",
                            "aliases": ["Tomoly"],
                        }
                    ]
                }
            ).entries
        )

        self.assertEqual(saved, 1)
        self.assertIn("Tomori => Tomori [character]", translator.glossary_text)
        self.assertIn("aliases: Tomoly", translator.glossary_text)

    def test_duplicate_source_and_alias_are_not_saved_twice(self):
        translator = self.make_translator("Tomori => Tomori [character] # aliases: Tomoly")

        saved = translator._save_glossary_entries(
            GlossaryResponse.model_validate(
                {
                    "entries": [
                        {"source": "Tomori", "target": "Tomori", "category": "character"},
                        {"source": "Yuuri", "target": "Tomoly", "category": "character"},
                    ]
                }
            ).entries
        )

        self.assertEqual(saved, 0)
        self.assertEqual(translator.glossary_text.count("[character]"), 1)
        self.assertTrue(any("deduplicated=2" in message for message in translator.logger.infos))

    def test_existing_manual_entry_is_preserved(self):
        translator = self.make_translator("Tomori => Manual Tomori [character] # chosen by editor")

        saved = translator._save_glossary_entries(
            GlossaryResponse.model_validate(
                {
                    "entries": [
                        {"source": "Tomori", "target": "Auto Tomori", "category": "character"}
                    ]
                }
            ).entries
        )

        self.assertEqual(saved, 0)
        self.assertIn("Manual Tomori", translator.glossary_text)
        self.assertNotIn("Auto Tomori", translator.glossary_text)

    def test_disabled_character_category_is_respected(self):
        translator = self.make_translator("", enabled={"place": "places"})

        saved = translator._save_glossary_entries(
            GlossaryResponse.model_validate(
                {
                    "entries": [
                        {"source": "Tomori", "target": "Tomori", "category": "name"}
                    ]
                }
            ).entries
        )

        self.assertEqual(saved, 0)
        self.assertEqual(translator.glossary_text, "")

    def test_positive_japanese_character_names_are_kept(self):
        translator = self.make_translator("")
        cases = [
            ("山田先輩", "Yamada-senpai"),
            ("めいちゃん", "Mei-chan"),
            ("稲光伸", "Inamitsu Shin"),
            ("稲光伸二", "Shinji Inamitsu"),
            ("池田", "Ikeda"),
            ("秋元", "Akimoto"),
            ("悠聖", "Yuusei"),
            ("高城さ～ん", "Takagi-san"),
            ("内田雪那", "Yukina Uchida"),
            ("ひかる", "Hikaru"),
        ]

        saved = translator._save_glossary_entries(
            GlossaryResponse.model_validate(
                {
                    "entries": [
                        {
                            "source": source,
                            "target": target,
                            "category": "name",
                            "confidence": 0.9,
                        }
                        for source, target in cases
                    ]
                }
            ).entries
        )

        self.assertEqual(saved, len(cases))
        self.assertIn("山田先輩 => Yamada-senpai [character]", translator.glossary_text)
        self.assertIn("高城さ～ん => Takagi-san [character]", translator.glossary_text)
        self.assertIn("ひかる => Hikaru [character]", translator.glossary_text)

    def test_negative_character_interjections_and_dialogue_are_rejected(self):
        translator = self.make_translator("")
        cases = [
            ("きゃッ！", "Ah!"),
            ("あっ", "Ah"),
            ("あんっ", "Ahh"),
            ("アッ", "Ah"),
            ("フッ！", "Hmph!"),
            ("チッ", "Tsk."),
            ("へへっ", "Hehe"),
            ("ウッ", "Ugh"),
            ("ごめんなさい！", "Sorry!"),
            ("待ってよ！", "Wait!"),
            ("タクシー止めていい？", "Can I call a taxi?"),
            ("もういいや", "That's enough."),
            ("。", "."),
            ("～～～ッッ！", "~~~!"),
        ]

        saved = translator._save_glossary_entries(
            GlossaryResponse.model_validate(
                {
                    "entries": [
                        {
                            "source": source,
                            "target": target,
                            "category": "name",
                            "confidence": 0.9,
                        }
                        for source, target in cases
                    ]
                }
            ).entries
        )

        self.assertEqual(saved, 0)
        self.assertEqual(translator.glossary_text, "")
        self.assertTrue(any("reason=interjection_or_sfx" in message for message in translator.logger.infos))
        self.assertTrue(any("reason=sentence_like" in message for message in translator.logger.infos))
        self.assertTrue(any("reason=punctuation_only" in message for message in translator.logger.infos))
        self.assertTrue(any("raw=14" in message and "rejected=14" in message for message in translator.logger.infos))

    def test_negative_dialogue_titles_are_rejected(self):
        translator = self.make_translator("", enabled={"title": "titles"})
        cases = [
            ("タクシー止めていい？", "Can I call a taxi?"),
            ("オメーが払えよな", "You'll pay for it."),
            ("待ってよ！", "Wait!"),
            ("ごめんなさい！", "Sorry!"),
            ("これも着ぐるみじゃない", "This isn't a costume either."),
        ]

        saved = translator._save_glossary_entries(
            GlossaryResponse.model_validate(
                {
                    "entries": [
                        {
                            "source": source,
                            "target": target,
                            "category": "title",
                            "confidence": 0.9,
                        }
                        for source, target in cases
                    ]
                }
            ).entries
        )

        self.assertEqual(saved, 0)
        self.assertEqual(translator.glossary_text, "")
        self.assertTrue(any("reason=invalid_title" in message for message in translator.logger.infos))


if __name__ == "__main__":
    unittest.main()
