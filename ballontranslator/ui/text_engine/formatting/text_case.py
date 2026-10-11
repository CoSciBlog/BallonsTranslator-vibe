"""Qt mapping for the persisted non-destructive text-case style."""

from qtpy.QtGui import QFont

from ballontranslator.utils.fontformat import (
    TEXT_CASE_LOWERCASE,
    TEXT_CASE_NORMAL,
    TEXT_CASE_UPPERCASE,
    normalize_text_case,
)


_TEXT_CASE_TO_CAPITALIZATION = {
    TEXT_CASE_NORMAL: QFont.Capitalization.MixedCase,
    TEXT_CASE_LOWERCASE: QFont.Capitalization.AllLowercase,
    TEXT_CASE_UPPERCASE: QFont.Capitalization.AllUppercase,
}
_CAPITALIZATION_TO_TEXT_CASE = {
    capitalization: text_case
    for text_case, capitalization in _TEXT_CASE_TO_CAPITALIZATION.items()
}


def text_case_capitalization(value: object) -> QFont.Capitalization:
    """Map persisted text-case state to Qt's display capitalization.

    >>> text_case_capitalization('uppercase') == QFont.Capitalization.AllUppercase
    True
    """
    return _TEXT_CASE_TO_CAPITALIZATION[normalize_text_case(value)]


def text_case_from_capitalization(
    capitalization: QFont.Capitalization,
) -> str:
    """Map Qt capitalization back to a persisted display mode."""
    return _CAPITALIZATION_TO_TEXT_CASE.get(
        capitalization,
        TEXT_CASE_NORMAL,
    )
