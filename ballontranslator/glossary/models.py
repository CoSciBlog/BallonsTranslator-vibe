"""Immutable data objects for versioned project glossaries."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


GLOSSARY_SCHEMA_VERSION = 1
ENTRY_SCHEMA_VERSION = 1


class GlossaryCategory(str, Enum):
    CHARACTER = 'Character'
    PLACE = 'Place'
    ORGANIZATION = 'Organization'
    TITLE = 'Title'
    HONORIFIC = 'Honorific'
    ITEM = 'Item'
    ABILITY = 'Ability'
    TERMINOLOGY = 'Terminology'
    CATCHPHRASE = 'Catchphrase'
    OTHER = 'Other'


class GlossaryOrigin(str, Enum):
    MANUAL = 'Manual'
    OCR = 'OCR'
    LLM = 'LLM'
    IMPORT = 'Import'


class GlossaryStatus(str, Enum):
    SUGGESTION = 'Suggestion'
    CONFIRMED = 'Confirmed'
    REJECTED = 'Rejected'


@dataclass(frozen=True)
class GlossaryEntry:
    """One source-to-target term with provenance and review state.

    >>> GlossaryEntry(id='term-1', original='勇者', translation='Held').original
    '勇者'
    """

    id: str
    original: str
    translation: str = ''
    source_language: str = ''
    target_language: str = ''
    category: GlossaryCategory = GlossaryCategory.OTHER
    aliases: Tuple[str, ...] = ()
    description: str = ''
    origin: GlossaryOrigin = GlossaryOrigin.MANUAL
    status: GlossaryStatus = GlossaryStatus.SUGGESTION
    protected: bool = False
    created_at: str = ''
    updated_at: str = ''
    confidence: Optional[float] = None
    schema_version: int = ENTRY_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'id': self.id,
            'original': self.original,
            'translation': self.translation,
            'source_language': self.source_language,
            'target_language': self.target_language,
            'category': self.category.value,
            'aliases': list(self.aliases),
            'description': self.description,
            'origin': self.origin.value,
            'status': self.status.value,
            'protected': self.protected,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'confidence': self.confidence,
        }


@dataclass(frozen=True)
class GlossaryDocument:
    """A versioned glossary source independent of project JSON."""

    schema_version: int = GLOSSARY_SCHEMA_VERSION
    glossary_id: str = 'project'
    entries: Tuple[GlossaryEntry, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            'schema_version': self.schema_version,
            'glossary_id': self.glossary_id,
            'entries': [entry.to_dict() for entry in self.entries],
        }
        if self.metadata:
            payload['metadata'] = dict(self.metadata)
        return payload
