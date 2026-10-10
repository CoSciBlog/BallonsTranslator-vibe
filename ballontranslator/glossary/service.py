"""Thread-safe business API for project glossaries."""

import threading
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from .models import (
    GlossaryCategory,
    GlossaryDocument,
    GlossaryEntry,
    GlossaryOrigin,
    GlossaryStatus,
)
from .persistence import GlossaryRepository, PathValue
from .validation import validate_entry, utc_now


class GlossaryServiceError(RuntimeError):
    """Base error for glossary business rules."""


class GlossaryNotFoundError(GlossaryServiceError):
    """An entry ID does not exist in the active glossary."""


class DuplicateGlossaryEntryError(GlossaryServiceError):
    """An original term or alias already belongs to another entry."""


class GlossaryProtectedError(GlossaryServiceError):
    """An automatic operation attempted to change a protected entry."""


@dataclass(frozen=True)
class GlossaryImportResult:
    added: int
    duplicates: int
    conflicts: int


@dataclass(frozen=True)
class GlossaryCandidateMergeResult:
    """Outcome of one atomic automatic-candidate merge."""

    added: int = 0
    updated: int = 0
    duplicates: int = 0
    conflicts: int = 0
    suppressed: int = 0


class GlossaryService:
    """Manage one glossary source without depending on Qt.

    The ``source_id`` argument leaves room for series or external sources while
    Phase 1 binds one service to the project's ``glossary.json``.

    >>> service = GlossaryService.in_memory()
    >>> service.create_entry(original='勇者', translation='Hero').translation
    'Hero'
    """

    def __init__(
        self,
        repository: Optional[GlossaryRepository],
        *,
        source_id: str = 'project',
        autosave: bool = True,
        create: bool = True,
    ) -> None:
        self.repository = repository
        self.source_id = source_id
        self.autosave = autosave
        self._lock = threading.RLock()
        self._document = GlossaryDocument(glossary_id=source_id)
        self._dirty = False
        self._closed = False
        if repository is not None:
            result = repository.load(create=create)
            self._document = result.document
            if result.migrated:
                self._dirty = True
                if autosave:
                    self.save()

    @classmethod
    def for_project(
        cls, project_directory: PathValue, *, autosave: bool = True
    ) -> 'GlossaryService':
        return cls(
            GlossaryRepository(Path(project_directory) / 'glossary.json'),
            source_id='project',
            autosave=autosave,
        )

    @classmethod
    def for_path(
        cls,
        path: PathValue,
        *,
        source_id: str,
        autosave: bool = True,
        create: bool = True,
    ) -> 'GlossaryService':
        """Open an explicitly named glossary source.

        >>> GlossaryService.for_path.__name__
        'for_path'
        """

        return cls(
            GlossaryRepository(path),
            source_id=source_id,
            autosave=autosave,
            create=create,
        )

    @classmethod
    def in_memory(cls) -> 'GlossaryService':
        return cls(None, autosave=False)

    @property
    def document(self) -> GlossaryDocument:
        with self._lock:
            return replace(self._document, metadata=dict(self._document.metadata))

    @property
    def entries(self) -> Tuple[GlossaryEntry, ...]:
        with self._lock:
            return self._document.entries

    @property
    def dirty(self) -> bool:
        return self._dirty

    def load(
        self, *, create: bool = True, discard_unsaved: bool = False
    ) -> GlossaryDocument:
        with self._lock:
            self._ensure_open()
            if self.repository is None:
                return self._document
            if self._dirty and not discard_unsaved:
                raise RuntimeError(
                    'Cannot reload a glossary with unsaved changes.'
                )
            result = self.repository.load(create=create)
            self._document = result.document
            self._dirty = result.migrated
            if result.migrated and self.autosave:
                self.save()
            return self._document

    def save(self, *, force: bool = False) -> bool:
        with self._lock:
            self._ensure_open()
            if self.repository is None or not self._dirty:
                return False
            written = self.repository.save(self._document, force=force)
            self._dirty = False
            return written

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._dirty:
                self.save()
            self._closed = True

    def has_external_changes(self) -> bool:
        with self._lock:
            self._ensure_open()
            return bool(
                self.repository and self.repository.has_external_changes()
            )

    def reload_if_changed(self) -> bool:
        with self._lock:
            self._ensure_open()
            if self.repository is None or not self.repository.has_external_changes():
                return False
            if self._dirty:
                raise RuntimeError('Cannot reload a glossary with unsaved changes.')
            self.load(create=False)
            return True

    def create_entry(self, **values: Any) -> GlossaryEntry:
        with self._lock:
            self._ensure_open()
            values.setdefault('origin', GlossaryOrigin.MANUAL.value)
            entry = validate_entry(values)
            duplicates = self.find_duplicates(entry.original, entry.aliases)
            if duplicates:
                raise DuplicateGlossaryEntryError(
                    'Term or alias already belongs to entry {}.'.format(
                        duplicates[0].id
                    )
                )
            self._replace_entries(self.entries + (entry,))
            return entry

    def update_entry(
        self, entry_id: str, *, automatic: bool = False, **changes: Any
    ) -> GlossaryEntry:
        with self._lock:
            current = self.get_entry(entry_id)
            if automatic and current.protected:
                raise GlossaryProtectedError(
                    'Protected entry {} cannot be changed automatically.'.format(
                        entry_id
                    )
                )
            for immutable in ('id', 'created_at', 'schema_version'):
                changes.pop(immutable, None)
            payload = current.to_dict()
            payload.update(changes)
            candidate = validate_entry(payload)
            if candidate == current:
                return current
            payload['updated_at'] = utc_now()
            updated = validate_entry(payload)
            duplicates = self.find_duplicates(
                updated.original, updated.aliases, exclude_id=entry_id
            )
            if duplicates:
                raise DuplicateGlossaryEntryError(
                    'Term or alias already belongs to entry {}.'.format(
                        duplicates[0].id
                    )
                )
            entries = tuple(
                updated if entry.id == entry_id else entry
                for entry in self.entries
            )
            if updated != current:
                self._replace_entries(entries)
            return updated

    def delete_entry(self, entry_id: str, *, automatic: bool = False) -> None:
        with self._lock:
            current = self.get_entry(entry_id)
            if automatic and current.protected:
                raise GlossaryProtectedError(
                    'Protected entry {} cannot be deleted automatically.'.format(
                        entry_id
                    )
                )
            self._replace_entries(
                tuple(entry for entry in self.entries if entry.id != entry_id)
            )

    def get_entry(self, entry_id: str) -> GlossaryEntry:
        with self._lock:
            self._ensure_open()
            for entry in self.entries:
                if entry.id == entry_id:
                    return entry
        raise GlossaryNotFoundError('Unknown glossary entry {}.'.format(entry_id))

    def search(
        self,
        query: str = '',
        *,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
        category: Optional[GlossaryCategory] = None,
        status: Optional[GlossaryStatus] = None,
    ) -> Tuple[GlossaryEntry, ...]:
        needle = _term_key(query)
        with self._lock:
            result = []
            for entry in self.entries:
                if source_language is not None and entry.source_language != source_language:
                    continue
                if target_language is not None and entry.target_language != target_language:
                    continue
                if category is not None and entry.category != GlossaryCategory(category):
                    continue
                if status is not None and entry.status != GlossaryStatus(status):
                    continue
                haystack = (
                    entry.original,
                    entry.translation,
                    entry.description,
                ) + entry.aliases
                if needle and not any(needle in _term_key(value) for value in haystack):
                    continue
                result.append(entry)
            return tuple(result)

    def add_alias(self, entry_id: str, alias: str) -> GlossaryEntry:
        current = self.get_entry(entry_id)
        alias = alias.strip()
        if not alias or _term_key(alias) in {
            _term_key(term) for term in (current.original,) + current.aliases
        }:
            return current
        return self.update_entry(entry_id, aliases=current.aliases + (alias,))

    def remove_alias(self, entry_id: str, alias: str) -> GlossaryEntry:
        current = self.get_entry(entry_id)
        key = _term_key(alias)
        aliases = tuple(item for item in current.aliases if _term_key(item) != key)
        if aliases == current.aliases:
            return current
        return self.update_entry(entry_id, aliases=aliases)

    def confirm_entry(self, entry_id: str) -> GlossaryEntry:
        return self.update_entry(entry_id, status=GlossaryStatus.CONFIRMED.value)

    def protect_entry(self, entry_id: str, protected: bool = True) -> GlossaryEntry:
        return self.update_entry(entry_id, protected=protected)

    def find_duplicates(
        self,
        original: str,
        aliases: Sequence[str] = (),
        *,
        exclude_id: Optional[str] = None,
    ) -> Tuple[GlossaryEntry, ...]:
        with self._lock:
            return _find_duplicates_in(
                self.entries,
                original,
                aliases,
                exclude_id=exclude_id,
            )

    def detect_duplicates(self) -> Tuple[Tuple[str, str], ...]:
        owners: Dict[str, str] = {}
        duplicates: List[Tuple[str, str]] = []
        with self._lock:
            for entry in self.entries:
                for term in (entry.original,) + entry.aliases:
                    key = _term_key(term)
                    owner = owners.get(key)
                    if owner is not None and owner != entry.id:
                        duplicates.append((owner, entry.id))
                    else:
                        owners[key] = entry.id
        return tuple(dict.fromkeys(duplicates))

    def import_file(self, path: PathValue) -> GlossaryImportResult:
        imported = GlossaryRepository(path).load(create=False).document
        return self.import_entries(imported.entries)

    def import_entries(
        self,
        incoming_entries: Sequence[GlossaryEntry],
    ) -> GlossaryImportResult:
        """Merge already validated entries and persist the batch once."""

        with self._lock:
            self._ensure_open()
            added: List[GlossaryEntry] = []
            duplicates = 0
            conflicts = 0
            used_ids = {entry.id for entry in self.entries}
            for incoming in incoming_entries:
                matches = _find_duplicates_in(
                    self.entries + tuple(added),
                    incoming.original,
                    incoming.aliases,
                )
                if matches:
                    if any(
                        match.translation == incoming.translation
                        for match in matches
                    ):
                        duplicates += 1
                    else:
                        conflicts += 1
                    continue
                if incoming.id in used_ids:
                    incoming = replace(incoming, id=str(uuid4()))
                used_ids.add(incoming.id)
                added.append(replace(incoming, origin=GlossaryOrigin.IMPORT))
            if added:
                self._replace_entries(self.entries + tuple(added))
            return GlossaryImportResult(
                added=len(added), duplicates=duplicates, conflicts=conflicts
            )

    def merge_automatic_candidates(
        self,
        candidates: Sequence[Dict[str, Any]],
    ) -> GlossaryCandidateMergeResult:
        """Merge suggestions once without changing reviewed/protected entries.

        Rejected terms are suppressed so repeated pages do not recreate them.
        Translation conflicts are reported and left for manual review. All
        accepted changes are persisted through one document replacement.
        """

        with self._lock:
            self._ensure_open()
            entries = list(self.entries)
            added = updated = duplicates = conflicts = suppressed = 0
            changed = False
            for values in candidates:
                payload = dict(values)
                payload['status'] = GlossaryStatus.SUGGESTION.value
                candidate = validate_entry(payload)
                matches = _find_duplicates_in(
                    entries,
                    candidate.original,
                    candidate.aliases,
                )
                if not matches:
                    entries.append(candidate)
                    added += 1
                    changed = True
                    continue

                if len(matches) > 1:
                    # One proposed alias set bridges multiple existing owners.
                    # Never guess which reviewed record should absorb it.
                    conflicts += 1
                    continue

                current = matches[0]
                if current.status == GlossaryStatus.REJECTED:
                    suppressed += 1
                    continue
                if current.status == GlossaryStatus.CONFIRMED or current.protected:
                    if (
                        candidate.translation
                        and current.translation
                        and candidate.translation != current.translation
                    ):
                        conflicts += 1
                    else:
                        duplicates += 1
                    continue
                if (
                    candidate.translation
                    and current.translation
                    and candidate.translation != current.translation
                ):
                    conflicts += 1
                    continue

                merged_aliases = tuple(dict.fromkeys(
                    current.aliases + candidate.aliases
                ))
                changes: Dict[str, Any] = {}
                if not current.translation and candidate.translation:
                    changes['translation'] = candidate.translation
                if merged_aliases != current.aliases:
                    other_duplicates = _find_duplicates_in(
                        entries,
                        current.original,
                        merged_aliases,
                        exclude_id=current.id,
                    )
                    if not other_duplicates:
                        changes['aliases'] = merged_aliases
                if (
                    candidate.confidence is not None
                    and (
                        current.confidence is None
                        or candidate.confidence > current.confidence
                    )
                ):
                    changes['confidence'] = candidate.confidence
                if changes:
                    candidate_payload = current.to_dict()
                    candidate_payload.update(changes)
                    candidate_payload['updated_at'] = utc_now()
                    merged = validate_entry(candidate_payload)
                    entries = [
                        merged if entry.id == current.id else entry
                        for entry in entries
                    ]
                    updated += 1
                    changed = True
                else:
                    duplicates += 1
            if changed:
                self._replace_entries(tuple(entries))
            return GlossaryCandidateMergeResult(
                added=added,
                updated=updated,
                duplicates=duplicates,
                conflicts=conflicts,
                suppressed=suppressed,
            )

    def export_file(self, path: PathValue) -> None:
        with self._lock:
            self._ensure_open()
            GlossaryRepository.export(path, self._document)

    def update_metadata(self, **changes: Any) -> bool:
        """Persist source assignments without modifying glossary entries."""

        with self._lock:
            self._ensure_open()
            metadata = dict(self._document.metadata)
            for key, value in changes.items():
                if value is None:
                    metadata.pop(key, None)
                else:
                    metadata[key] = value
            if metadata == self._document.metadata:
                return False
            self._document = replace(self._document, metadata=metadata)
            self._dirty = True
            if self.autosave:
                self.save()
            return True

    def _replace_entries(self, entries: Tuple[GlossaryEntry, ...]) -> None:
        self._document = replace(self._document, entries=entries)
        self._dirty = True
        if self.autosave:
            self.save()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError('Glossary service is closed.')


def _term_key(value: str) -> str:
    return unicodedata.normalize('NFKC', value).strip().casefold()


def _find_duplicates_in(
    entries: Sequence[GlossaryEntry],
    original: str,
    aliases: Sequence[str],
    *,
    exclude_id: Optional[str] = None,
) -> Tuple[GlossaryEntry, ...]:
    candidate_keys = {_term_key(term) for term in (original,) + tuple(aliases)}
    candidate_keys.discard('')
    duplicates = []
    for entry in entries:
        if entry.id == exclude_id:
            continue
        entry_keys = {
            _term_key(term) for term in (entry.original,) + entry.aliases
        }
        if candidate_keys & entry_keys:
            duplicates.append(entry)
    return tuple(duplicates)
