"""Safe UTF-8 JSON persistence for project glossaries."""

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from ballontranslator.utils.logger import logger as LOGGER

from .migration import migrate_payload
from .models import GLOSSARY_SCHEMA_VERSION, GlossaryDocument
from .validation import GlossaryValidationError, validate_document


PathValue = Union[str, os.PathLike]


class GlossaryPersistenceError(RuntimeError):
    """A glossary could not be read or written safely."""


class GlossaryCorruptError(GlossaryPersistenceError):
    """The glossary exists but is not valid JSON or model data."""


class UnsupportedGlossarySchemaError(GlossaryPersistenceError):
    """The glossary was written by an unsupported future schema."""


class GlossaryConflictError(GlossaryPersistenceError):
    """The glossary changed outside this service since it was loaded."""


@dataclass(frozen=True)
class GlossaryLoadResult:
    document: GlossaryDocument
    migrated: bool = False


class GlossaryRepository:
    """Own one glossary file and detect changes made by other writers."""

    def __init__(self, path: PathValue) -> None:
        self.path = Path(path)
        self._signature: Optional[str] = None

    def load(self, *, create: bool = True) -> GlossaryLoadResult:
        if not self.path.exists():
            if not create:
                raise FileNotFoundError(str(self.path))
            document = GlossaryDocument()
            self._signature = None
            self.save(document)
            return GlossaryLoadResult(document=document)
        try:
            raw = self.path.read_bytes()
            payload = json.loads(raw.decode('utf-8-sig'))
            payload, migrated = migrate_payload(payload)
            version = payload.get('schema_version')
            if type(version) is not int or version < 1:
                raise GlossaryValidationError('Invalid glossary schema version.')
            if version > GLOSSARY_SCHEMA_VERSION:
                raise UnsupportedGlossarySchemaError(
                    'Glossary schema {} is newer than supported schema {}.'.format(
                        version, GLOSSARY_SCHEMA_VERSION
                    )
                )
            document = validate_document(payload)
        except UnsupportedGlossarySchemaError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise GlossaryCorruptError(
                'Could not load glossary "{}": {}.'.format(self.path, error)
            ) from error
        self._signature = _signature(raw)
        return GlossaryLoadResult(document=document, migrated=migrated)

    def save(self, document: GlossaryDocument, *, force: bool = False) -> bool:
        validated = validate_document(document.to_dict())
        encoded = _encode(validated)
        current = self._read_signature()
        if not force and current != self._signature:
            raise GlossaryConflictError(
                'Glossary "{}" changed outside this service.'.format(self.path)
            )
        if current == _signature(encoded):
            self._signature = current
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='wb',
                dir=str(self.path.parent),
                prefix=self.path.name + '.',
                suffix='.tmp',
                delete=False,
            ) as temporary:
                temporary_path = temporary.name
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        except OSError as error:
            raise GlossaryPersistenceError(
                'Could not save glossary "{}": {}.'.format(self.path, error)
            ) from error
        finally:
            if temporary_path and os.path.exists(temporary_path):
                try:
                    os.unlink(temporary_path)
                except OSError:
                    LOGGER.warning('Could not remove glossary temp file %s.', temporary_path)
        self._signature = _signature(encoded)
        return True

    def has_external_changes(self) -> bool:
        return self._read_signature() != self._signature

    @classmethod
    def export(cls, path: PathValue, document: GlossaryDocument) -> None:
        repository = cls(path)
        repository._signature = repository._read_signature()
        repository.save(document, force=True)

    def _read_signature(self) -> Optional[str]:
        try:
            return _signature(self.path.read_bytes())
        except FileNotFoundError:
            return None
        except OSError as error:
            raise GlossaryPersistenceError(
                'Could not inspect glossary "{}": {}.'.format(self.path, error)
            ) from error


def _encode(document: GlossaryDocument) -> bytes:
    return (
        json.dumps(document.to_dict(), ensure_ascii=False, indent=2) + '\n'
    ).encode('utf-8')


def _signature(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
