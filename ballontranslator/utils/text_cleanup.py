import re


TRANSLATION_LINEBREAK_RE = re.compile(r"[ \t]*(?:\r\n|\r|\n)[ \t]*")


def remove_translation_linebreaks(text: str) -> str:
    if not text:
        return ""
    return TRANSLATION_LINEBREAK_RE.sub(" ", str(text))
