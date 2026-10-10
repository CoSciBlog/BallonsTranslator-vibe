"""Select reviewed project glossary entries for one translation request."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from .models import GlossaryEntry, GlossaryStatus


@dataclass(frozen=True)
class SelectedGlossaryEntry:
    """One request-local mapping selected from a project glossary.

    ``source`` is the spelling which matched the current OCR text. Keeping the
    canonical term and all aliases as metadata lets an LLM resolve spelling
    variants without applying unsafe replacements to the source text.

    >>> SelectedGlossaryEntry('勇者', 'Hero', '勇者').translation
    'Hero'
    """

    source: str
    translation: str
    canonical: str
    aliases: Tuple[str, ...] = ()
    category: str = 'Other'
    entry_id: str = ''


def term_occurs(text: str, term: str) -> bool:
    """Match a Unicode term without treating Latin word fragments as terms.

    Han, kana and Hangul commonly occur without whitespace, so those scripts
    use literal substring matching. Alphabetic scripts with word separation
    require boundaries at alphanumeric edges.

    >>> term_occurs('A HERO appears', 'hero')
    True
    >>> term_occurs('superhero', 'hero')
    False
    >>> term_occurs('勇者様', '勇者')
    True
    """

    normalized_text = _normalize(text)
    normalized_term = _normalize(term)
    if not normalized_term:
        return False
    start = 0
    require_boundaries = _uses_separated_script(normalized_term)
    while True:
        index = normalized_text.find(normalized_term, start)
        if index < 0:
            return False
        end = index + len(normalized_term)
        if not require_boundaries or (
            _left_boundary(normalized_text, index)
            and _right_boundary(normalized_text, end)
        ):
            return True
        start = index + 1


def select_relevant_entries(
    entries: Iterable[GlossaryEntry],
    sources: Iterable[str],
    *,
    source_language: str = '',
    target_language: str = '',
    max_entries: int = 32,
    token_budget: int = 1200,
) -> Tuple[SelectedGlossaryEntry, ...]:
    """Return relevant confirmed entries under deterministic request budgets.

    The byte-count estimate is deliberately conservative for UTF-8 prompt
    content. It caps additions without requiring a provider tokenizer and is
    stable across providers and offline tests.
    """

    if max_entries <= 0 or token_budget <= 0:
        return ()
    source_text = '\n'.join(str(item) for item in sources if item is not None)
    selected = []
    used_budget = 0
    for entry in entries:
        if entry.status != GlossaryStatus.CONFIRMED or not entry.translation:
            continue
        if not _language_matches(entry.source_language, source_language):
            continue
        if not _language_matches(entry.target_language, target_language):
            continue
        matched = next(
            (
                spelling
                for spelling in (entry.original,) + entry.aliases
                if term_occurs(source_text, spelling)
            ),
            None,
        )
        if matched is None:
            continue
        candidate = SelectedGlossaryEntry(
            source=matched,
            translation=entry.translation,
            canonical=entry.original,
            aliases=entry.aliases,
            category=entry.category.value,
            entry_id=entry.id,
        )
        cost = _prompt_token_upper_bound(candidate)
        if used_budget + cost > token_budget:
            continue
        selected.append(candidate)
        used_budget += cost
        if len(selected) >= max_entries:
            break
    return tuple(selected)


def _normalize(value: str) -> str:
    return unicodedata.normalize('NFKC', str(value)).casefold()


def _language_matches(saved: str, active: str) -> bool:
    return not saved or not active or _normalize(saved) == _normalize(active)


def _uses_separated_script(value: str) -> bool:
    for character in value:
        name = unicodedata.name(character, '')
        if any(script in name for script in ('CJK', 'HIRAGANA', 'KATAKANA', 'HANGUL')):
            return False
    return any(character.isalnum() for character in value)


def _word_character(character: Optional[str]) -> bool:
    return bool(character) and (
        character.isalnum()
        or character == '_'
        or unicodedata.category(character).startswith('M')
    )


def _left_boundary(text: str, index: int) -> bool:
    return index == 0 or not _word_character(text[index - 1])


def _right_boundary(text: str, index: int) -> bool:
    return index == len(text) or not _word_character(text[index])


def _prompt_token_upper_bound(entry: SelectedGlossaryEntry) -> int:
    payload = {
        'source': entry.source,
        'translation': entry.translation,
        'canonical': entry.canonical,
        'aliases': entry.aliases,
        'category': entry.category,
    }
    return max(
        1,
        len(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')),
    )
