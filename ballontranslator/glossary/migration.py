"""Import adapters for legacy 1.4-vibe and simple glossary payloads."""

import re
from typing import Any, Dict, Iterable, List, Tuple
from uuid import NAMESPACE_URL, uuid5

from .models import (
    GLOSSARY_SCHEMA_VERSION,
    GlossaryCategory,
    GlossaryOrigin,
    GlossaryStatus,
)
from .validation import utc_now


_LEGACY_LINE = re.compile(
    r'^\s*(?P<source>.+?)\s*=>\s*(?P<target>.*?)(?:\s*\[(?P<category>[^\]]+)\])?(?:\s*#\s*(?P<note>.*))?\s*$'
)
_CATEGORY_ALIASES = {
    'character': GlossaryCategory.CHARACTER.value,
    'name': GlossaryCategory.CHARACTER.value,
    'place': GlossaryCategory.PLACE.value,
    'location': GlossaryCategory.PLACE.value,
    'organization': GlossaryCategory.ORGANIZATION.value,
    'organisation': GlossaryCategory.ORGANIZATION.value,
    'title': GlossaryCategory.TITLE.value,
    'honorific': GlossaryCategory.HONORIFIC.value,
    'item': GlossaryCategory.ITEM.value,
    'ability': GlossaryCategory.ABILITY.value,
    'attack': GlossaryCategory.ABILITY.value,
    'term': GlossaryCategory.TERMINOLOGY.value,
    'terminology': GlossaryCategory.TERMINOLOGY.value,
    'catchphrase': GlossaryCategory.CATCHPHRASE.value,
    'other': GlossaryCategory.OTHER.value,
}


def migrate_payload(payload: Any) -> Tuple[Dict[str, Any], bool]:
    """Return a current document payload and whether migration was needed.

    >>> migrate_payload({'entries': 'Hero => Held [character]'})[0]['entries'][0]['original']
    'Hero'
    """

    if isinstance(payload, dict) and 'schema_version' in payload:
        return payload, False

    if isinstance(payload, list):
        raw_entries = payload
        metadata: Dict[str, Any] = {'migrated_from': 'entry-list'}
    elif isinstance(payload, str):
        raw_entries = list(_legacy_lines(payload))
        metadata = {'migrated_from': '1.4-vibe'}
    elif isinstance(payload, dict):
        raw_entries = []
        entries = payload.get('entries', payload.get('text', payload.get('glossary', '')))
        if isinstance(entries, str):
            raw_entries.extend(_legacy_lines(entries))
        elif isinstance(entries, list):
            raw_entries.extend(entries)
        reference = payload.get('reference_entries', payload.get('reference', ''))
        if isinstance(reference, str):
            raw_entries.extend(_legacy_lines(reference))
        preferred = payload.get('preferred_targets', '')
        if isinstance(preferred, str):
            raw_entries.extend(_legacy_preferred_targets(preferred))
        metadata = {
            key: value
            for key, value in {
                'migrated_from': '1.4-vibe',
                'legacy_prompt': payload.get('prompt', ''),
                'legacy_reference_prompt': payload.get('reference_prompt', ''),
            }.items()
            if value
        }
    else:
        raise ValueError('Unsupported glossary payload.')

    now = utc_now()
    converted = [
        _convert_entry(entry, index=index, now=now)
        for index, entry in enumerate(raw_entries)
    ]
    return {
        'schema_version': GLOSSARY_SCHEMA_VERSION,
        'glossary_id': 'project',
        'entries': converted,
        'metadata': metadata,
    }, True


def _legacy_lines(text: str) -> Iterable[Dict[str, Any]]:
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith('#'):
            continue
        match = _LEGACY_LINE.match(clean)
        if not match:
            raise ValueError(
                'Invalid legacy glossary line {!r}; expected source => target.'.format(
                    clean
                )
            )
        values = match.groupdict()
        yield {
            'source': values['source'].strip(),
            'target': values['target'].strip(),
            'category': values.get('category') or 'term',
            'note': values.get('note') or '',
        }


def _legacy_preferred_targets(text: str) -> Iterable[Dict[str, Any]]:
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith('#'):
            continue
        note = ''
        if '#' in clean:
            clean, note = (part.strip() for part in clean.split('#', 1))
        category = 'term'
        category_match = re.search(r'\s*\[([^\]]+)\]\s*$', clean)
        if category_match:
            category = category_match.group(1).strip()
            clean = clean[:category_match.start()].strip()
        if clean:
            yield {
                'source': clean,
                'target': clean,
                'category': category,
                'note': note,
            }


def _convert_entry(entry: Any, *, index: int, now: str) -> Dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError('Legacy glossary entries must be objects.')
    original = entry.get(
        'original', entry.get('source', entry.get('src', entry.get('term', '')))
    )
    translation = entry.get(
        'translation',
        entry.get('target', entry.get('dst', entry.get('replacement', ''))),
    )
    category = _CATEGORY_ALIASES.get(
        str(entry.get('category', 'other')).strip().casefold(),
        GlossaryCategory.OTHER.value,
    )
    description = entry.get(
        'description', entry.get('note', entry.get('info', ''))
    )
    aliases = entry.get('aliases', [])
    if isinstance(aliases, str):
        aliases = [part.strip() for part in aliases.split(',') if part.strip()]
    stable_id = str(
        uuid5(
            NAMESPACE_URL,
            'ballontranslator:legacy:{}:{}:{}'.format(index, original, translation),
        )
    )
    return {
        'schema_version': 1,
        'id': entry.get('id') or stable_id,
        'original': original,
        'translation': translation,
        'source_language': entry.get('source_language', ''),
        'target_language': entry.get('target_language', ''),
        'category': category,
        'aliases': aliases,
        'description': description if isinstance(description, str) else '',
        'origin': GlossaryOrigin.IMPORT.value,
        'status': entry.get('status', GlossaryStatus.SUGGESTION.value),
        'protected': bool(entry.get('protected', False)),
        'created_at': entry.get('created_at') or now,
        'updated_at': entry.get('updated_at') or now,
        'confidence': entry.get('confidence'),
    }
