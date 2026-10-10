import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from qtpy.QtCore import QTranslator


ROOT = Path(__file__).resolve().parents[1]
TRANSLATE_DIR = ROOT / 'resources' / 'translate'
PLACEHOLDER_RE = re.compile(
    r'https?://\S+|\{[^{}\n]+\}|%\d*[$]?[a-zA-Z]|</?[^>\n]+>|\\[nrt]'
)
CONTAMINATION_MARKERS = (
    '"source":',
    '"text":',
    '"type":',
    'source_lang_code',
    'target_lang_code',
    '[[BT',
    'ZXQ',
)


def active_messages(path: Path):
    root = ET.parse(path).getroot()
    for context in root.findall('context'):
        context_name = context.findtext('name') or ''
        for message in context.findall('message'):
            translation = message.find('translation')
            if translation is not None and translation.get('type') in {'obsolete', 'vanished'}:
                continue
            yield context_name, message.findtext('source') or '', translation


class TranslationCatalogTest(unittest.TestCase):
    def test_english_and_german_catalogs_are_complete_and_aligned(self):
        catalogs = {}
        for language in ('en_US', 'de_DE'):
            messages = list(active_messages(TRANSLATE_DIR / f'{language}.ts'))
            catalogs[language] = {(context, source) for context, source, _ in messages}
            self.assertGreater(len(messages), 1200)
            for context, source, translation in messages:
                with self.subTest(language=language, context=context, source=source):
                    self.assertIsNotNone(translation)
                    self.assertNotEqual(translation.get('type'), 'unfinished')
                    translated = translation.text or ''
                    self.assertEqual(
                        sorted(PLACEHOLDER_RE.findall(source)),
                        sorted(PLACEHOLDER_RE.findall(translated)),
                    )
                    self.assertEqual(source[:len(source) - len(source.lstrip())], translated[:len(translated) - len(translated.lstrip())])
                    self.assertEqual(source[len(source.rstrip()):], translated[len(translated.rstrip()):])
                    for marker in CONTAMINATION_MARKERS:
                        if marker not in source:
                            self.assertNotIn(marker, translated)
                    if language == 'en_US':
                        self.assertEqual(translated, source)
        self.assertEqual(catalogs['en_US'], catalogs['de_DE'])

    def test_german_qm_contains_requested_translator_language_names(self):
        translator = QTranslator()
        self.assertTrue(translator.load(str(TRANSLATE_DIR / 'de_DE.qm')))
        expected = {
            'Chinese (Simplified)': 'Chinesisch (vereinfacht)',
            'Chinese (Traditional)': 'Chinesisch (traditionell)',
            'Korean': 'Koreanisch',
            'Vietnamese': 'Vietnamesisch',
            'Czech': 'Tschechisch',
            'Hungarian': 'Ungarisch',
            'Portuguese': 'Portugiesisch',
            'Russian': 'Russisch',
            'Spanish': 'Spanisch',
            'Turkish': 'Türkisch',
            'Ukrainian': 'Ukrainisch',
            'Romanian': 'Rumänisch',
            'Japanese': 'Japanisch',
        }
        self.assertEqual(
            {
                source: translator.translate('TranslatorLanguage', source)
                for source in expected
            },
            expected,
        )

    def test_german_qm_contains_llm_memory_setting(self):
        translator = QTranslator()
        self.assertTrue(translator.load(str(TRANSLATE_DIR / 'de_DE.qm')))
        self.assertEqual(
            translator.translate(
                'ConfigPanel',
                'Unload local models before LLM requests',
            ),
            'Lokale Modelle vor LLM-Anfragen entladen',
        )


if __name__ == '__main__':
    unittest.main()
