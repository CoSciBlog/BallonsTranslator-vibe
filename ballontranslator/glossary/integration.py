"""Translation-pipeline coordination for the project glossary backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple, TYPE_CHECKING, Union

from .extraction import GlossaryCandidate, GlossaryCandidateExtractor
from .matching import SelectedGlossaryEntry, select_relevant_entries, term_occurs
from .service import GlossaryCandidateMergeResult, GlossaryService
from .workspace import GlossaryWorkspace

if TYPE_CHECKING:
    from ballontranslator.modules.context.glossary import GlossaryEntry as PromptGlossaryEntry


@dataclass(frozen=True)
class GlossaryConsistencyIssue:
    """A confirmed source term whose requested translation was not observed."""

    entry_id: str
    source: str
    expected_translation: str


def project_prompt_entries(
    service: Optional[Union[GlossaryService, GlossaryWorkspace]],
    sources: Iterable[str],
    *,
    source_language: str = '',
    target_language: str = '',
    max_entries: int = 32,
    token_budget: int = 1200,
) -> Tuple['PromptGlossaryEntry', ...]:
    """Adapt relevant confirmed project entries to the existing LLM contract."""

    if service is None:
        return ()
    entries = (
        tuple(item.entry for item in service.effective_entries())
        if isinstance(service, GlossaryWorkspace)
        else service.entries
    )
    selected = select_relevant_entries(
        entries,
        sources,
        source_language=source_language,
        target_language=target_language,
        max_entries=max_entries,
        token_budget=token_budget,
    )
    return tuple(_as_prompt_entry(entry) for entry in selected)


def merge_prompt_entries(
    project_entries: Sequence['PromptGlossaryEntry'],
    explicit_entries: Sequence['PromptGlossaryEntry'],
) -> Tuple['PromptGlossaryEntry', ...]:
    """Combine prompt mappings with reviewed project entries taking priority."""

    merged = []
    seen = set()
    for entry in tuple(project_entries) + tuple(explicit_entries):
        key = entry.source.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    return tuple(merged)


def extract_and_store_candidates(
    service: Optional[GlossaryService],
    source_texts: Sequence[str],
    translated_texts: Sequence[str],
    *,
    extractor: GlossaryCandidateExtractor,
    source_language: str = '',
    target_language: str = '',
    extra_candidates: Sequence[GlossaryCandidate] = (),
    categories: Optional[Sequence[str]] = None,
    confirm_new: bool = False,
) -> GlossaryCandidateMergeResult:
    """Extract and atomically store suggestions after successful translation."""

    if service is None:
        return GlossaryCandidateMergeResult()
    candidates = tuple(extractor.extract(source_texts, translated_texts)) + tuple(
        extra_candidates
    )
    allowed = set(categories) if categories is not None else None
    candidates = tuple(
        candidate for candidate in candidates
        if allowed is None or candidate.category.value in allowed
    )
    payloads = [
        {
            'original': candidate.original,
            'translation': candidate.translation,
            'source_language': source_language,
            'target_language': target_language,
            'category': candidate.category.value,
            'aliases': candidate.aliases,
            'description': candidate.description,
            'origin': candidate.origin.value,
            'confidence': candidate.confidence,
        }
        for candidate in candidates
    ]
    result = service.merge_automatic_candidates(payloads)
    if confirm_new and payloads:
        # Empty mappings are not usable glossary decisions. Keep candidates
        # without a target as suggestions until a later translation can fill
        # them or the user reviews them explicitly.
        originals = {
            payload['original'].casefold()
            for payload in payloads
            if payload['translation']
        }
        for entry in service.entries:
            if (
                entry.status.value == 'Suggestion'
                and entry.original.casefold() in originals
            ):
                service.confirm_entry(entry.id)
    return result


def check_translation_consistency(
    selected_entries: Sequence[SelectedGlossaryEntry],
    source_texts: Sequence[str],
    translated_texts: Sequence[str],
) -> Tuple[GlossaryConsistencyIssue, ...]:
    """Report possible misses without rewriting provider output."""

    source = '\n'.join(source_texts)
    translation = '\n'.join(translated_texts)
    issues = []
    for entry in selected_entries:
        if not term_occurs(source, entry.source):
            continue
        if term_occurs(translation, entry.translation):
            continue
        issues.append(GlossaryConsistencyIssue(
            entry_id=entry.entry_id,
            source=entry.source,
            expected_translation=entry.translation,
        ))
    return tuple(issues)


def _as_prompt_entry(entry: SelectedGlossaryEntry) -> 'PromptGlossaryEntry':
    from ballontranslator.modules.context.glossary import GlossaryEntry

    details = [
        'confirmed project entry',
        'category={}'.format(entry.category),
        'canonical={}'.format(entry.canonical),
    ]
    if entry.aliases:
        details.append('aliases={}'.format(', '.join(entry.aliases)))
    return GlossaryEntry(entry.source, entry.translation, '; '.join(details))
