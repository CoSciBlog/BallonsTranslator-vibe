"""Qt-free glossary candidate extraction independent of translation providers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence, Tuple

from .models import GlossaryCategory, GlossaryOrigin


_WORD_PATTERN = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)
_QUOTED_PATTERN = re.compile(r'[「『“\"]([^」』”\"]{2,64})[」』”\"]')
_SENTENCE_PUNCTUATION = re.compile(r'[.!?。！？,:;：；\n]')
_COMMON_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'but', 'chapter', 'for', 'from',
    'he', 'her', 'his', 'i', 'if', 'in', 'into', 'it', 'me', 'my', 'no',
    'of', 'on', 'or', 'our', 'page', 'she', 'so', 'that', 'the', 'their',
    'they', 'this', 'to', 'we', 'what', 'when', 'where', 'who', 'why',
    'with', 'you', 'your',
}
_TITLE_HINTS = {
    'captain', 'chief', 'doctor', 'dr', 'emperor', 'empress', 'general',
    'king', 'lady', 'lord', 'master', 'miss', 'mr', 'mrs', 'ms', 'prince',
    'princess', 'professor', 'queen', 'saint', 'sir', '先生', '先輩', '様',
    'さん', '씨', '님',
}
_PLACE_HINTS = {
    'bridge', 'castle', 'city', 'district', 'forest', 'harbor', 'island',
    'kingdom', 'lake', 'mount', 'mountain', 'palace', 'river', 'shrine',
    'station', 'street', 'temple', 'tower', 'town', 'village',
}
_ORGANIZATION_HINTS = {
    'association', 'church', 'clan', 'club', 'company', 'council', 'guild',
    'institute', 'office', 'order', 'squad', 'team',
}
_ABILITY_HINTS = {'art', 'attack', 'blast', 'magic', 'spell', 'strike', 'technique'}
_ITEM_HINTS = {'amulet', 'armor', 'blade', 'key', 'ring', 'shield', 'sword'}


@dataclass(frozen=True)
class GlossaryCandidate:
    """One unreviewed term proposed by an OCR or LLM extractor.

    >>> GlossaryCandidate('Sakura', '桜').origin.value
    'OCR'
    """

    original: str
    translation: str = ''
    category: GlossaryCategory = GlossaryCategory.OTHER
    aliases: Tuple[str, ...] = ()
    description: str = ''
    origin: GlossaryOrigin = GlossaryOrigin.OCR
    confidence: float = 0.5


class GlossaryCandidateExtractor(Protocol):
    """Extension point for a future separately configured extraction model."""

    def extract(
        self,
        source_texts: Sequence[str],
        translated_texts: Sequence[str] = (),
    ) -> Tuple[GlossaryCandidate, ...]: ...


class RuleBasedGlossaryExtractor:
    """Conservatively find term-shaped OCR text without any model call."""

    def extract(
        self,
        source_texts: Sequence[str],
        translated_texts: Sequence[str] = (),
    ) -> Tuple[GlossaryCandidate, ...]:
        candidates = []
        for index, source in enumerate(source_texts):
            source = _clean_text(source)
            target = (
                _clean_text(translated_texts[index])
                if index < len(translated_texts)
                else ''
            )
            exact_term = _standalone_term(source)
            if exact_term:
                candidates.append(self._candidate(
                    exact_term,
                    target,
                    0.76,
                    aligned_translation=True,
                ))
            for quoted in _QUOTED_PATTERN.findall(source):
                quoted = _clean_term(quoted)
                if _valid_term(quoted):
                    candidates.append(self._candidate(quoted, '', 0.63))
            candidates.extend(self._proper_name_candidates(source))
        return _deduplicate(candidates)

    def _proper_name_candidates(self, text: str) -> Iterable[GlossaryCandidate]:
        words = list(_WORD_PATTERN.finditer(text))
        index = 0
        while index < len(words):
            word = words[index].group(0)
            if not _looks_proper(word):
                index += 1
                continue
            phrase = [word]
            cursor = index + 1
            while cursor < len(words) and len(phrase) < 4:
                gap = text[words[cursor - 1].end():words[cursor].start()]
                following = words[cursor].group(0)
                if not gap.isspace() or not _looks_proper(following):
                    break
                phrase.append(following)
                cursor += 1
            term = _clean_term(' '.join(phrase))
            if _valid_term(term):
                yield self._candidate(term, '', 0.58)
            index = cursor

    @staticmethod
    def _candidate(
        term: str,
        translation: str,
        confidence: float,
        *,
        aligned_translation: bool = False,
    ) -> GlossaryCandidate:
        # An exact OCR block has a trustworthy aligned result even when the
        # target language needs more words or punctuation than the source.
        # Sub-term candidates must stay conservative because their translation
        # cannot be inferred from the complete translated block.
        safe_translation = (
            _safe_aligned_translation(translation)
            if aligned_translation
            else _safe_target_term(translation)
        )
        return GlossaryCandidate(
            original=term,
            translation=translation if safe_translation else '',
            category=classify_term(term),
            confidence=confidence,
        )


def parse_llm_candidates(response: str) -> Tuple[GlossaryCandidate, ...]:
    """Validate a data-only JSON response from an optional external extractor.

    This parser deliberately performs no request. A later configured extractor
    can call its own model once and feed the response here.
    """

    try:
        payload = json.loads(response)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError('Glossary extraction response is not valid JSON.') from error
    rows = payload.get('candidates') if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError('Glossary extraction response must contain a candidate list.')
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        original = _clean_term(str(row.get('original', '')))
        if not _candidate_term_valid(original):
            continue
        try:
            category = GlossaryCategory(str(row.get('category', 'Other')))
        except ValueError:
            category = GlossaryCategory.OTHER
        try:
            confidence = min(1.0, max(0.0, float(row.get('confidence', 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        aliases = tuple(
            alias for alias in (
                _clean_term(str(value))
                for value in row.get('aliases', ())
                if isinstance(value, str)
            )
            if _candidate_term_valid(alias) and alias.casefold() != original.casefold()
        ) if isinstance(row.get('aliases', ()), (list, tuple)) else ()
        candidates.append(GlossaryCandidate(
            original=original,
            translation=_clean_text(str(row.get('translation', ''))),
            category=category,
            aliases=aliases,
            description=_clean_text(str(row.get('description', ''))),
            origin=GlossaryOrigin.LLM,
            confidence=confidence,
        ))
    return _deduplicate(candidates)


def classify_term(term: str) -> GlossaryCategory:
    words = {word.casefold().strip(".'") for word in _WORD_PATTERN.findall(term)}
    if words & _TITLE_HINTS or any(term.endswith(hint) for hint in _TITLE_HINTS):
        return GlossaryCategory.HONORIFIC
    if words & _PLACE_HINTS:
        return GlossaryCategory.PLACE
    if words & _ORGANIZATION_HINTS:
        return GlossaryCategory.ORGANIZATION
    if words & _ABILITY_HINTS:
        return GlossaryCategory.ABILITY
    if words & _ITEM_HINTS:
        return GlossaryCategory.ITEM
    if len(words) <= 3 and any(_looks_proper(word) for word in words):
        return GlossaryCategory.CHARACTER
    return GlossaryCategory.TERMINOLOGY


def _standalone_term(text: str) -> str:
    term = _clean_term(text)
    if not _valid_term(term) or _SENTENCE_PUNCTUATION.search(term):
        return ''
    words = _WORD_PATTERN.findall(term)
    if not words or len(words) > 5:
        return ''
    if any(_looks_proper(word) for word in words):
        return term
    if any(term.endswith(hint) for hint in _TITLE_HINTS):
        return term
    if _contains_unseparated_script(term) and len(term) <= 12:
        return term
    return ''


def _looks_proper(word: str) -> bool:
    return (
        len(word) >= 2
        and word.casefold() not in _COMMON_WORDS
        and (word[0].isupper() or (len(word) >= 3 and word.isupper()))
    )


def _valid_term(term: str) -> bool:
    return 2 <= len(term) <= 64 and len(term.split()) <= 5


def _candidate_term_valid(term: str) -> bool:
    return _valid_term(term) and not _SENTENCE_PUNCTUATION.search(term)


def _safe_target_term(term: str) -> bool:
    return (
        1 <= len(term) <= 64
        and len(term.split()) <= 5
        and not _SENTENCE_PUNCTUATION.search(term)
    )


def _safe_aligned_translation(term: str) -> bool:
    """Accept a complete translated block while bounding persisted data."""

    return 1 <= len(term) <= 512


def _contains_unseparated_script(term: str) -> bool:
    return bool(re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', term))


def _clean_text(value: str) -> str:
    return re.sub(r'\s+', ' ', value or '').strip()


def _clean_term(value: str) -> str:
    return _clean_text(value).strip(' \t\r\n\"\'.,!?;:()[]{}')


def _deduplicate(candidates: Iterable[GlossaryCandidate]) -> Tuple[GlossaryCandidate, ...]:
    result = []
    seen = set()
    for candidate in candidates:
        key = candidate.original.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return tuple(result)
