import re
import unicodedata


_LANGUAGE_ALIASES = {
    'auto': 'auto',
    'auto detect': 'auto',
    'chinese': 'zh',
    'simplified chinese': 'zh',
    'traditional chinese': 'zh',
    'japanese': 'ja',
    'korean': 'ko',
    'english': 'en',
    'vietnamese': 'vi',
    'czech': 'cs',
    'dutch': 'nl',
    'french': 'fr',
    'german': 'de',
    'hungarian': 'hu',
    'italian': 'it',
    'polish': 'pl',
    'portuguese': 'pt',
    'brazilian portuguese': 'pt',
    'romanian': 'ro',
    'russian': 'ru',
    'spanish': 'es',
    'turkish': 'tr',
    'ukrainian': 'uk',
    'thai': 'th',
    'arabic': 'ar',
    'hindi': 'hi',
    'malayalam': 'ml',
    'tamil': 'ta',
}


def canonical_ocr_language(language) -> str:
    text = unicodedata.normalize('NFKC', str(language or '')).strip().casefold()
    if not text:
        return ''
    text = re.sub(r'\s*\([^)]*\)\s*$', '', text).strip()
    if text in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[text]
    code = text.replace('_', '-').split('-', 1)[0]
    if re.fullmatch(r'[a-z]{2,3}', code):
        return code
    return text


def ocr_languages_compatible(source_language, configured_language) -> bool:
    source = canonical_ocr_language(source_language)
    configured = canonical_ocr_language(configured_language)
    return not source or source == 'auto' or not configured or configured == 'auto' or source == configured
