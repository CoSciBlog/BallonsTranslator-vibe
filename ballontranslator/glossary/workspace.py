"""Combine project, series, and read-only reference glossaries."""

from __future__ import annotations

import os
import threading
import unicodedata
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ballontranslator.utils.logger import logger as LOGGER

from .models import GlossaryEntry, GlossaryOrigin, GlossaryStatus
from .persistence import GlossaryPersistenceError
from .service import GlossaryCandidateMergeResult, GlossaryService


SOURCE_ASSIGNMENTS_KEY = 'sources'


@dataclass(frozen=True)
class GlossarySource:
    source_id: str
    kind: str
    path: str
    service: GlossaryService
    writable: bool


@dataclass(frozen=True)
class EffectiveGlossaryEntry:
    entry: GlossaryEntry
    source_id: str
    source_kind: str
    source_path: str
    writable: bool
    priority: int


@dataclass(frozen=True)
class GlossaryConflict:
    term: str
    winner: EffectiveGlossaryEntry
    alternatives: Tuple[EffectiveGlossaryEntry, ...]


@dataclass(frozen=True)
class GlossaryMergeResult:
    added: int = 0
    duplicates: int = 0
    conflicts: int = 0


class GlossaryWorkspace:
    """Own all glossary sources associated with one project.

    The project source remains the only automatic write target. References are
    deliberately read-only and series writes happen only through explicit API
    calls, which makes the same object safe for a future chapter queue.

    >>> workspace = GlossaryWorkspace.in_memory()
    >>> workspace.project.create_entry(original='勇者', translation='Hero')
    GlossaryEntry(...)
    """

    def __init__(
        self,
        project: GlossaryService,
        *,
        project_directory: str = '',
    ) -> None:
        self.project = project
        self.project_directory = os.path.abspath(project_directory) if project_directory else ''
        self._series: Optional[GlossarySource] = None
        self._references: List[GlossarySource] = []
        self._lock = threading.RLock()
        self._closed = False
        self._completion_callbacks: List[Callable[['GlossaryWorkspace'], None]] = []
        self._restoring_assignments = False

    @classmethod
    def for_project(
        cls,
        project_directory: os.PathLike | str,
        *,
        create: bool = True,
    ) -> 'GlossaryWorkspace':
        directory = os.path.abspath(os.fspath(project_directory))
        project = GlossaryService.for_path(
            os.path.join(directory, 'glossary.json'),
            source_id='project',
            create=create,
        )
        workspace = cls(project, project_directory=directory)
        workspace._restore_assignments()
        return workspace

    @classmethod
    def in_memory(cls) -> 'GlossaryWorkspace':
        return cls(GlossaryService.in_memory())

    @property
    def series(self) -> Optional[GlossarySource]:
        return self._series

    @property
    def references(self) -> Tuple[GlossarySource, ...]:
        return tuple(self._references)

    @property
    def sources(self) -> Tuple[GlossarySource, ...]:
        project_path = str(self.project.repository.path) if self.project.repository else ''
        project = GlossarySource('project', 'project', project_path, self.project, True)
        extra = ((self._series,) if self._series else ()) + tuple(self._references)
        return (project,) + extra

    def assign_series(self, path: os.PathLike | str, *, create: bool = True) -> GlossarySource:
        with self._lock:
            self._ensure_open()
            resolved = self._resolve_path(path)
            current = self._series
            if current and _same_path(current.path, resolved):
                return current
            service = GlossaryService.for_path(
                resolved, source_id='series', autosave=True, create=create
            )
            if current:
                current.service.close()
            self._series = GlossarySource('series', 'series', resolved, service, True)
            self._persist_assignments()
            return self._series

    def clear_series(self) -> None:
        with self._lock:
            if self._series:
                self._series.service.close()
                self._series = None
                self._persist_assignments()

    def add_reference(self, path: os.PathLike | str) -> GlossarySource:
        with self._lock:
            self._ensure_open()
            resolved = self._resolve_path(path)
            for source in self._references:
                if _same_path(source.path, resolved):
                    return source
            source_id = 'reference:{}'.format(len(self._references) + 1)
            service = GlossaryService.for_path(
                resolved, source_id=source_id, autosave=False, create=False
            )
            source = GlossarySource(source_id, 'reference', resolved, service, False)
            self._references.append(source)
            self._persist_assignments()
            return source

    def remove_reference(self, path: os.PathLike | str) -> bool:
        with self._lock:
            resolved = self._resolve_path(path)
            for source in tuple(self._references):
                if _same_path(source.path, resolved):
                    source.service.close()
                    self._references.remove(source)
                    self._persist_assignments()
                    return True
            return False

    def effective_entries(self) -> Tuple[EffectiveGlossaryEntry, ...]:
        """Return one winner per term plus source trace in priority order."""

        with self._lock:
            self._ensure_open()
            ranked = self._ranked_entries()
            winners: List[EffectiveGlossaryEntry] = []
            claimed: Dict[str, EffectiveGlossaryEntry] = {}
            for candidate in ranked:
                keys = {_term_key(term) for term in (candidate.entry.original,) + candidate.entry.aliases}
                keys.discard('')
                if any(key in claimed for key in keys):
                    continue
                winners.append(candidate)
                for key in keys:
                    claimed[key] = candidate
            return tuple(winners)

    def source_entries(self) -> Tuple[EffectiveGlossaryEntry, ...]:
        """Return all entries with source metadata in priority order."""

        with self._lock:
            self._ensure_open()
            return tuple(self._ranked_entries())

    def conflicts(self) -> Tuple[GlossaryConflict, ...]:
        with self._lock:
            grouped: Dict[str, List[EffectiveGlossaryEntry]] = {}
            display: Dict[str, str] = {}
            for candidate in self._ranked_entries():
                for term in (candidate.entry.original,) + candidate.entry.aliases:
                    key = _term_key(term)
                    if key:
                        grouped.setdefault(key, []).append(candidate)
                        display.setdefault(key, term)
            conflicts = []
            for key, candidates in grouped.items():
                translations = {_term_key(item.entry.translation) for item in candidates if item.entry.translation}
                unique = _unique_candidates(candidates)
                if len(translations) > 1 and len(unique) > 1:
                    conflicts.append(GlossaryConflict(display[key], unique[0], tuple(unique[1:])))
            return tuple(conflicts)

    def merge_into_project(self, path: os.PathLike | str) -> GlossaryMergeResult:
        result = self.project.import_file(path)
        return GlossaryMergeResult(result.added, result.duplicates, result.conflicts)

    def merge_project_candidates(
        self,
        candidates: Sequence[Dict[str, object]],
    ) -> GlossaryCandidateMergeResult:
        """Store new automatic terms in the project source only."""

        return self.project.merge_automatic_candidates(candidates)

    def promote_confirmed_to_series(self) -> GlossaryMergeResult:
        with self._lock:
            if self._series is None:
                raise RuntimeError('No series glossary is assigned.')
            confirmed = tuple(
                entry for entry in self.project.entries
                if entry.status == GlossaryStatus.CONFIRMED
            )
            result = self._series.service.import_entries(confirmed)
            return GlossaryMergeResult(
                result.added, result.duplicates, result.conflicts
            )

    def on_project_completed(self, callback: Callable[['GlossaryWorkspace'], None]) -> None:
        with self._lock:
            if callback not in self._completion_callbacks:
                self._completion_callbacks.append(callback)

    def complete_project(self) -> None:
        with self._lock:
            self.save()
            callbacks = tuple(self._completion_callbacks)
        for callback in callbacks:
            callback(self)

    def save(self) -> None:
        with self._lock:
            self.project.save()
            if self._series:
                self._series.service.save()

    def reload_external_changes(self) -> Tuple[str, ...]:
        changed = []
        with self._lock:
            for source in self.sources:
                if source.service.reload_if_changed():
                    changed.append(source.source_id)
        return tuple(changed)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self.save()
            for source in self.sources:
                source.service.close()
            self._closed = True

    def _ranked_entries(self) -> List[EffectiveGlossaryEntry]:
        ranked = []
        for source in self.sources:
            for entry in source.service.entries:
                ranked.append(EffectiveGlossaryEntry(
                    entry=entry,
                    source_id=source.source_id,
                    source_kind=source.kind,
                    source_path=source.path,
                    writable=source.writable,
                    priority=_priority(source.kind, entry),
                ))
        ranked.sort(key=lambda item: (item.priority, item.entry.created_at, item.entry.id))
        return ranked

    def _restore_assignments(self) -> None:
        data = self.project.document.metadata.get(SOURCE_ASSIGNMENTS_KEY, {})
        if not isinstance(data, dict):
            return
        self._restoring_assignments = True
        try:
            series = data.get('series')
            if isinstance(series, str) and series:
                try:
                    self.assign_series(series, create=False)
                except (GlossaryPersistenceError, OSError, ValueError) as error:
                    LOGGER.warning('Ignored unavailable series glossary %s: %s', series, error)
            references = data.get('references', ())
            if isinstance(references, list):
                for path in references:
                    if isinstance(path, str) and path:
                        try:
                            self.add_reference(path)
                        except (GlossaryPersistenceError, OSError, ValueError) as error:
                            LOGGER.warning('Ignored unavailable reference glossary %s: %s', path, error)
        finally:
            self._restoring_assignments = False

    def _persist_assignments(self) -> None:
        if self._restoring_assignments:
            return
        series = self._portable_path(self._series.path) if self._series else ''
        references = [self._portable_path(source.path) for source in self._references]
        self.project.update_metadata(**{
            SOURCE_ASSIGNMENTS_KEY: {'series': series, 'references': references}
        })

    def _resolve_path(self, path: os.PathLike | str) -> str:
        value = os.fspath(path)
        if not os.path.isabs(value) and self.project_directory:
            value = os.path.join(self.project_directory, value)
        return os.path.abspath(value)

    def _portable_path(self, path: str) -> str:
        if not self.project_directory:
            return path
        try:
            return os.path.relpath(path, self.project_directory)
        except ValueError:
            return path

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError('Glossary workspace is closed.')


def _priority(kind: str, entry: GlossaryEntry) -> int:
    confirmed = entry.status == GlossaryStatus.CONFIRMED
    if kind == 'project' and confirmed:
        return 10
    if kind == 'series' and confirmed:
        return 20
    if kind == 'reference' and confirmed:
        return 25
    if kind == 'project':
        return 30 if entry.origin != GlossaryOrigin.LLM else 50
    if kind == 'series':
        return 40 if entry.origin != GlossaryOrigin.LLM else 55
    return 45 if entry.origin != GlossaryOrigin.LLM else 60


def _term_key(value: str) -> str:
    return unicodedata.normalize('NFKC', value).strip().casefold()


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def _unique_candidates(
    candidates: Iterable[EffectiveGlossaryEntry],
) -> List[EffectiveGlossaryEntry]:
    result = []
    seen = set()
    for candidate in candidates:
        key = (candidate.source_id, candidate.entry.id)
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result
