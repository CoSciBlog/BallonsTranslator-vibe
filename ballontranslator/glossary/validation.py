"""Validation and normalization for glossary data."""

from datetime import datetime, timezone
import unicodedata
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar
from uuid import uuid4

from .models import (
    ENTRY_SCHEMA_VERSION,
    GlossaryCategory,
    GlossaryDocument,
    GlossaryEntry,
    GlossaryOrigin,
    GlossaryStatus,
)


class GlossaryValidationError(ValueError):
    """Glossary data violates a stable model contract."""


EnumValue = TypeVar('EnumValue')


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace(
        '+00:00', 'Z'
    )


def normalize_term(value: str) -> str:
    """Trim outer whitespace without changing Unicode content.

    >>> normalize_term('  魔王  ')
    '魔王'
    """

    if not isinstance(value, str):
        raise GlossaryValidationError('Glossary terms must be strings.')
    return value.strip()


def validate_entry(
    payload: Dict[str, Any],
    *,
    default_origin: GlossaryOrigin = GlossaryOrigin.MANUAL,
    now: Optional[str] = None,
) -> GlossaryEntry:
    if not isinstance(payload, dict):
        raise GlossaryValidationError('A glossary entry must be an object.')
    version = payload.get('schema_version', ENTRY_SCHEMA_VERSION)
    if type(version) is not int or version != ENTRY_SCHEMA_VERSION:
        raise GlossaryValidationError(
            'Unsupported glossary entry schema version {!r}.'.format(version)
        )

    original = normalize_term(payload.get('original', ''))
    if not original:
        raise GlossaryValidationError('A glossary entry needs an original term.')
    translation = normalize_term(payload.get('translation', ''))
    entry_id = normalize_term(payload.get('id', '')) or str(uuid4())
    source_language = _string(payload.get('source_language', ''), 'source_language')
    target_language = _string(payload.get('target_language', ''), 'target_language')
    description = _string(payload.get('description', ''), 'description')
    aliases = _aliases(payload.get('aliases', ()), original)
    category = _enum_value(
        GlossaryCategory,
        payload.get('category', GlossaryCategory.OTHER.value),
        'category',
    )
    origin = _enum_value(
        GlossaryOrigin,
        payload.get('origin', default_origin.value),
        'origin',
    )
    status = _enum_value(
        GlossaryStatus,
        payload.get('status', GlossaryStatus.SUGGESTION.value),
        'status',
    )
    protected = payload.get('protected', False)
    if type(protected) is not bool:
        raise GlossaryValidationError('protected must be a boolean.')
    confidence = payload.get('confidence')
    if confidence is not None:
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise GlossaryValidationError('confidence must be a number or null.')
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise GlossaryValidationError('confidence must be between 0 and 1.')

    timestamp = now or utc_now()
    created_at = _timestamp(payload.get('created_at', timestamp), 'created_at')
    updated_at = _timestamp(payload.get('updated_at', created_at), 'updated_at')
    return GlossaryEntry(
        id=entry_id,
        original=original,
        translation=translation,
        source_language=source_language.strip(),
        target_language=target_language.strip(),
        category=category,
        aliases=aliases,
        description=description,
        origin=origin,
        status=status,
        protected=protected,
        created_at=created_at,
        updated_at=updated_at,
        confidence=confidence,
        schema_version=version,
    )


def validate_document(payload: Dict[str, Any]) -> GlossaryDocument:
    if not isinstance(payload, dict):
        raise GlossaryValidationError('A glossary document must be an object.')
    entries = payload.get('entries', [])
    if not isinstance(entries, list):
        raise GlossaryValidationError('Glossary entries must be an array.')
    glossary_id = _string(payload.get('glossary_id', 'project'), 'glossary_id').strip()
    if not glossary_id:
        raise GlossaryValidationError('glossary_id cannot be empty.')
    metadata = payload.get('metadata', {})
    if not isinstance(metadata, dict):
        raise GlossaryValidationError('metadata must be an object.')
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise GlossaryValidationError(
                'Glossary entry {} must be an object.'.format(index + 1)
            )
        for required in ('id', 'created_at', 'updated_at'):
            if not isinstance(entry.get(required), str) or not entry[required].strip():
                raise GlossaryValidationError(
                    'Glossary entry {} needs a stable {}.'.format(
                        index + 1, required
                    )
                )
    validated_entries = tuple(validate_entry(entry) for entry in entries)
    entry_ids = [entry.id for entry in validated_entries]
    if len(entry_ids) != len(set(entry_ids)):
        raise GlossaryValidationError('Glossary entry IDs must be unique.')
    return GlossaryDocument(
        schema_version=payload['schema_version'],
        glossary_id=glossary_id,
        entries=validated_entries,
        metadata=dict(metadata),
    )


def _string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise GlossaryValidationError('{} must be a string.'.format(field_name))
    return value


def _aliases(value: Any, original: str) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise GlossaryValidationError('aliases must be an array of strings.')
    original_key = _unicode_key(original)
    result: List[str] = []
    seen = {original_key}
    for alias in value:
        alias = normalize_term(alias)
        key = _unicode_key(alias)
        if alias and key not in seen:
            seen.add(key)
            result.append(alias)
    return tuple(result)


def _unicode_key(value: str) -> str:
    return unicodedata.normalize('NFKC', value).casefold()


def _enum_value(
    enum_type: Type[EnumValue], value: Any, field_name: str
) -> EnumValue:
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        choices = ', '.join(item.value for item in enum_type)
        raise GlossaryValidationError(
            '{} must be one of: {}.'.format(field_name, choices)
        )


def _timestamp(value: Any, field_name: str) -> str:
    value = _string(value, field_name).strip()
    if not value:
        raise GlossaryValidationError('{} cannot be empty.'.format(field_name))
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise GlossaryValidationError(
            '{} must be an ISO 8601 timestamp.'.format(field_name)
        ) from error
    return value
