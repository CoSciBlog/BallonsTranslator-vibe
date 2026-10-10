from __future__ import annotations

import json
import os
import os.path as osp
import tempfile
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


HISTORY_FILENAME = 'pipeline_history.json'
SCHEMA_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace(
        '+00:00', 'Z'
    )


class PipelineHistoryStore:
    """Atomically persist pipeline execution history outside project JSON.

    >>> PipelineHistoryStore.filename
    'pipeline_history.json'
    """

    filename = HISTORY_FILENAME

    def __init__(self, directory: str) -> None:
        self.directory = osp.abspath(directory)
        self.path = osp.join(self.directory, self.filename)
        self._lock = threading.RLock()

    def load(self) -> List[Dict[str, Any]]:
        with self._lock:
            if not osp.exists(self.path):
                return []
            with open(self.path, 'r', encoding='utf-8') as history_file:
                payload = json.load(history_file)
            if (
                not isinstance(payload, dict)
                or payload.get('schema_version') != SCHEMA_VERSION
                or not isinstance(payload.get('entries'), list)
            ):
                raise ValueError('Unsupported or malformed pipeline history file.')
            return deepcopy(payload['entries'])

    def start(self, kind: str, details: Optional[Dict[str, Any]] = None) -> str:
        now = utc_now()
        entry_id = str(uuid.uuid4())
        entry = {
            'id': entry_id,
            'kind': str(kind),
            'status': 'running',
            'started_at': iso_timestamp(now),
            'ended_at': None,
            'duration_seconds': None,
            'details': deepcopy(details or {}),
        }
        with self._lock:
            entries = self.load()
            entries.append(entry)
            self._save(entries)
        return entry_id

    def finish(
        self,
        entry_id: str,
        status: str,
        error: str = '',
    ) -> bool:
        ended = utc_now()
        with self._lock:
            entries = self.load()
            for entry in reversed(entries):
                if entry.get('id') != entry_id:
                    continue
                started = _parse_timestamp(entry.get('started_at'))
                entry['status'] = str(status)
                entry['ended_at'] = iso_timestamp(ended)
                entry['duration_seconds'] = round(
                    max(0.0, (ended - started).total_seconds()), 3
                )
                if error:
                    entry['error'] = str(error)
                self._save(entries)
                return True
        return False

    def _save(self, entries: List[Dict[str, Any]]) -> None:
        os.makedirs(self.directory, exist_ok=True)
        payload = {
            'schema_version': SCHEMA_VERSION,
            'entries': entries,
        }
        descriptor, temporary_path = tempfile.mkstemp(
            prefix='.pipeline_history.', suffix='.tmp', dir=self.directory
        )
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as output:
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if osp.exists(temporary_path):
                os.unlink(temporary_path)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        return utc_now()
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(
            timezone.utc
        )
    except ValueError:
        return utc_now()
