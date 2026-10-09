"""Localized display names for stable translator language identifiers."""

from qtpy.QtCore import QCoreApplication


# Translator modules and saved configuration use these identifiers as stable
# keys.  Keep them unchanged and translate only the user-facing labels.
TRANSLATOR_LANGUAGE_NAMES = {
    'Auto': 'Auto-detect',
    '简体中文': 'Chinese (Simplified)',
    '繁體中文': 'Chinese (Traditional)',
    '日本語': 'Japanese',
    'English': 'English',
    '한국어': 'Korean',
    'Tiếng Việt': 'Vietnamese',
    'čeština': 'Czech',
    'Nederlands': 'Dutch',
    'Français': 'French',
    'Deutsch': 'German',
    'magyar nyelv': 'Hungarian',
    'Italiano': 'Italian',
    'Polski': 'Polish',
    'Português': 'Portuguese',
    'Brazilian Portuguese': 'Brazilian Portuguese',
    'limba română': 'Romanian',
    'русский язык': 'Russian',
    'Español': 'Spanish',
    'Türk dili': 'Turkish',
    'украї́нська мо́ва': 'Ukrainian',
    'Thai': 'Thai',
    'Arabic': 'Arabic',
    'Hindi': 'Hindi',
    'Malayalam': 'Malayalam',
    'Tamil': 'Tamil',
}


def _translation_catalog() -> None:
    """Expose dynamic language labels to Qt's static translation extractor."""

    QCoreApplication.translate('TranslatorLanguage', 'Auto-detect')
    QCoreApplication.translate('TranslatorLanguage', 'Chinese (Simplified)')
    QCoreApplication.translate('TranslatorLanguage', 'Chinese (Traditional)')
    QCoreApplication.translate('TranslatorLanguage', 'Japanese')
    QCoreApplication.translate('TranslatorLanguage', 'English')
    QCoreApplication.translate('TranslatorLanguage', 'Korean')
    QCoreApplication.translate('TranslatorLanguage', 'Vietnamese')
    QCoreApplication.translate('TranslatorLanguage', 'Czech')
    QCoreApplication.translate('TranslatorLanguage', 'Dutch')
    QCoreApplication.translate('TranslatorLanguage', 'French')
    QCoreApplication.translate('TranslatorLanguage', 'German')
    QCoreApplication.translate('TranslatorLanguage', 'Hungarian')
    QCoreApplication.translate('TranslatorLanguage', 'Italian')
    QCoreApplication.translate('TranslatorLanguage', 'Polish')
    QCoreApplication.translate('TranslatorLanguage', 'Portuguese')
    QCoreApplication.translate('TranslatorLanguage', 'Brazilian Portuguese')
    QCoreApplication.translate('TranslatorLanguage', 'Romanian')
    QCoreApplication.translate('TranslatorLanguage', 'Russian')
    QCoreApplication.translate('TranslatorLanguage', 'Spanish')
    QCoreApplication.translate('TranslatorLanguage', 'Turkish')
    QCoreApplication.translate('TranslatorLanguage', 'Ukrainian')
    QCoreApplication.translate('TranslatorLanguage', 'Thai')
    QCoreApplication.translate('TranslatorLanguage', 'Arabic')
    QCoreApplication.translate('TranslatorLanguage', 'Hindi')
    QCoreApplication.translate('TranslatorLanguage', 'Malayalam')
    QCoreApplication.translate('TranslatorLanguage', 'Tamil')


def translator_language_name(identifier: str) -> str:
    """Return a localized label without changing the translator identifier."""

    source = TRANSLATOR_LANGUAGE_NAMES.get(identifier, identifier)
    return QCoreApplication.translate('TranslatorLanguage', source)
