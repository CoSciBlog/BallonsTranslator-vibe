from __future__ import annotations

import copy
import csv
import io
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ballontranslator.glossary import GlossaryWorkspace
from ballontranslator.utils.llm_profiles import LLMProfile, profile_from_config
from ballontranslator.utils.proj_imgtrans import ProjImgTrans, TextBlkEncoder
from ballontranslator.utils.textblock import TextBlock


@dataclass(frozen=True)
class TranslationBenchmarkVariant:
    """Detached LLM configuration used by one benchmark run.

    >>> TranslationBenchmarkVariant.from_profile(LLMProfile(name='Local', model='m')).model
    'm'
    """

    profile: LLMProfile

    @classmethod
    def from_profile(cls, profile: LLMProfile) -> "TranslationBenchmarkVariant":
        return cls(profile_from_config(profile))

    @property
    def id(self) -> str:
        return self.profile.id

    @property
    def label(self) -> str:
        name = self.profile.name or self.profile.id or 'LLM'
        return f'{name} — {self.profile.model}' if self.profile.model else name

    @property
    def model(self) -> str:
        return self.profile.model

    def public_settings(self) -> Dict[str, object]:
        """Return reproducibility fields without credentials or endpoints.

        >>> 'api_key' in TranslationBenchmarkVariant.from_profile(LLMProfile()).public_settings()
        False
        """

        profile = self.profile
        return {
            'profile_id': profile.id,
            'profile_name': profile.name,
            'backend': profile.backend,
            'model': profile.model,
            'max_tokens': profile.max_tokens,
            'ollama_context_length': profile.ollama_context_length,
            'temperature': profile.temperature,
            'top_p': profile.top_p,
            'frequency_penalty': profile.frequency_penalty,
            'presence_penalty': profile.presence_penalty,
            'thinking_level': profile.thinking_level,
            'use_glossary': profile.use_glossary,
            'review_translation': profile.review_translation,
            'google_first_pass': profile.google_first_pass,
            'use_adjacent_page_context': profile.use_adjacent_page_context,
            'json_schema_response_format': profile.json_schema_response_format,
            'low_vram_mode': profile.low_vram_mode,
            'prompt': profile.prompt,
        }


@dataclass
class TranslationBenchmarkRun:
    variant: TranslationBenchmarkVariant
    duration_seconds: float = 0.0
    status: str = 'completed'
    error: str = ''
    translations: Dict[str, List[str]] = field(default_factory=dict)
    preview_pages: Dict[str, List[TextBlock]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            'variant': self.variant.public_settings(),
            'label': self.variant.label,
            'duration_seconds': self.duration_seconds,
            'status': self.status,
            'error': self.error,
            'translations': copy.deepcopy(self.translations),
        }

    def summary_dict(self) -> Dict[str, object]:
        """Return run metadata for a manifest without duplicating results."""

        result = self.to_dict()
        result.pop('translations')
        return result


@dataclass
class TranslationBenchmarkReport:
    pages: List[str]
    sources: Dict[str, List[str]]
    source_language: str
    target_language: str
    text_detector: str
    ocr: str
    detection_ocr_seconds: float
    runs: List[TranslationBenchmarkRun]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cancelled: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            'format': 'ballonstranslator-translation-benchmark-v2',
            'created_at': self.created_at,
            'source_language': self.source_language,
            'target_language': self.target_language,
            'text_detector': self.text_detector,
            'ocr': self.ocr,
            'pages': list(self.pages),
            'detection_ocr_seconds': self.detection_ocr_seconds,
            'cancelled': self.cancelled,
            'sources': copy.deepcopy(self.sources),
            'runs': [run.to_dict() for run in self.runs],
        }

    def to_csv(self) -> str:
        """Return aligned block results for spreadsheet comparison."""

        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(
            ['page', 'block', 'source']
            + [run.variant.label for run in self.runs]
        )
        for page in self.pages:
            sources = self.sources.get(page, [])
            for block_index, source in enumerate(sources, start=1):
                row = [page, block_index, source]
                for run in self.runs:
                    translations = run.translations.get(page, [])
                    row.append(
                        translations[block_index - 1]
                        if block_index <= len(translations)
                        else ''
                    )
                writer.writerow(row)
        return output.getvalue()

    def manifest_dict(
        self,
        result_files: Sequence[str],
    ) -> Dict[str, object]:
        """Return shared benchmark metadata and links to per-profile files."""

        result = self.to_dict()
        result['format'] = 'ballonstranslator-translation-benchmark-manifest-v2'
        result['runs'] = [
            {
                **run.summary_dict(),
                'result_file': filename,
            }
            for run, filename in zip(self.runs, result_files)
        ]
        return result

    def result_dict(self, run: TranslationBenchmarkRun) -> Dict[str, object]:
        """Return one self-contained, credential-free profile result."""

        return {
            'format': 'ballonstranslator-translation-benchmark-result-v2',
            'created_at': self.created_at,
            'source_language': self.source_language,
            'target_language': self.target_language,
            'text_detector': self.text_detector,
            'ocr': self.ocr,
            'pages': list(self.pages),
            'detection_ocr_seconds': self.detection_ocr_seconds,
            'cancelled': self.cancelled,
            'sources': copy.deepcopy(self.sources),
            'run': run.to_dict(),
            # Complete frozen blocks make each result independently inspectable
            # and preserve the geometry used by the live page preview.
            'page_results': copy.deepcopy(run.preview_pages),
        }


@dataclass(frozen=True)
class TranslationBenchmarkSaveResult:
    directory: str
    manifest_path: str
    result_paths: Tuple[str, ...]


def benchmark_result_directory_name(
    report: TranslationBenchmarkReport,
    sequence: int = 1,
) -> str:
    """Return a readable, collision-suffixable directory for one benchmark.

    >>> report = TranslationBenchmarkReport([], {}, '', '', '', '', 0.0, [], created_at='2026-11-02T12:34:56.123456+00:00')
    >>> benchmark_result_directory_name(report)
    'translation-benchmark-20261102T123456123456Z'
    >>> benchmark_result_directory_name(report, 2)
    'translation-benchmark-20261102T123456123456Z-2'
    """

    created_at = datetime.fromisoformat(report.created_at.replace('Z', '+00:00'))
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    timestamp = created_at.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    suffix = '' if sequence == 1 else f'-{sequence}'
    return f'translation-benchmark-{timestamp}{suffix}'


def _result_filename(run: TranslationBenchmarkRun, index: int) -> str:
    profile_name = run.variant.profile.name or run.variant.id or 'profile'
    slug = re.sub(r'[^a-z0-9]+', '-', profile_name.lower()).strip('-')
    if not slug:
        slug = 'profile'
    return f'{index:02d}-{slug}.json'


def _write_json(path: str, payload: Mapping[str, object]) -> None:
    with open(path, 'x', encoding='utf-8', newline='\n') as stream:
        json.dump(
            payload,
            stream,
            ensure_ascii=False,
            indent=2,
            cls=TextBlkEncoder,
        )
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def save_benchmark_results(
    project_directory: str,
    report: TranslationBenchmarkReport,
) -> TranslationBenchmarkSaveResult:
    """Save one manifest and one JSON file per profile in a unique folder.

    The complete file set is assembled in a same-volume temporary directory and
    published with one rename, so readers never observe a partial benchmark.
    """

    if not project_directory or not os.path.isdir(project_directory):
        raise FileNotFoundError(project_directory)

    sequence = 1
    target = os.path.join(
        project_directory,
        benchmark_result_directory_name(report, sequence),
    )
    while os.path.exists(target):
        sequence += 1
        target = os.path.join(
            project_directory,
            benchmark_result_directory_name(report, sequence),
        )

    # Keep the temporary directory on the same volume so os.replace remains
    # atomic and the final directory appears only after every file is durable.
    temporary = os.path.join(
        project_directory,
        f'.{os.path.basename(target)}.{uuid.uuid4().hex}.tmp',
    )
    os.mkdir(temporary)
    try:
        result_files = [
            _result_filename(run, index)
            for index, run in enumerate(report.runs, start=1)
        ]
        for run, filename in zip(report.runs, result_files):
            _write_json(
                os.path.join(temporary, filename),
                report.result_dict(run),
            )
        _write_json(
            os.path.join(temporary, 'benchmark.json'),
            report.manifest_dict(result_files),
        )
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            shutil.rmtree(temporary)
    return TranslationBenchmarkSaveResult(
        directory=target,
        manifest_path=os.path.join(target, 'benchmark.json'),
        result_paths=tuple(
            os.path.join(target, filename) for filename in result_files
        ),
    )


def clone_project_for_benchmark(
    project: ProjImgTrans,
    pages: Optional[Mapping[str, Sequence]] = None,
) -> ProjImgTrans:
    """Clone runtime project context without opening persistence services.

    Every project page remains available for history and adjacent-page context,
    while ``pages`` can replace the benchmarked pages with the frozen OCR result.

    >>> project = ProjImgTrans()
    >>> project.pages = {'001.png': []}
    >>> project._image_info = {'001.png': {'finish_code': 0}}
    >>> clone_project_for_benchmark(project).pages is project.pages
    False
    """

    clone = ProjImgTrans()
    clone.type = project.type
    clone.directory = project.directory
    clone.proj_path = project.proj_path
    clone.current_img = project.current_img
    clone.pages = copy.deepcopy(project.pages)
    if pages is not None:
        for page, blocks in pages.items():
            if page in clone.pages:
                clone.pages[page] = copy.deepcopy(list(blocks))
    ordered_pages = list(clone.pages)
    clone._pagename2idx = {
        page: index for index, page in enumerate(ordered_pages)
    }
    clone._idx2pagename = {
        index: page for index, page in enumerate(ordered_pages)
    }
    clone._image_info = copy.deepcopy(project._image_info)
    for page in ordered_pages:
        clone._image_info.setdefault(page, {'finish_code': 0})
        clone._image_info[page].setdefault('finish_code', 0)
    clone._llm_compact_memory = copy.deepcopy(project._llm_compact_memory)
    # Prompt lookup uses an in-memory snapshot. Deliberately omit
    # glossary_service so neither reload nor automatic extraction can touch the
    # live project glossary while a benchmark is running.
    clone.glossary_workspace = _snapshot_glossary_workspace(project)
    clone.glossary_service = None
    return clone


def _snapshot_glossary_workspace(project: ProjImgTrans) -> Optional[GlossaryWorkspace]:
    source_workspace = project.glossary_workspace
    source_service = project.glossary_service
    if source_workspace is not None:
        entries = [
            copy.deepcopy(item.entry)
            for item in source_workspace.effective_entries()
        ]
    elif source_service is not None:
        entries = copy.deepcopy(list(source_service.entries))
    else:
        return None
    workspace = GlossaryWorkspace.in_memory()
    workspace.project.import_entries(entries)
    return workspace


def page_texts(project: ProjImgTrans, pages: Iterable[str], attr: str) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for page in pages:
        blocks = project.pages.get(page, [])
        if attr == 'source':
            result[page] = [block.get_text() for block in blocks]
        elif attr == 'translation':
            result[page] = [str(block.translation or '') for block in blocks]
        else:
            raise ValueError(f'Unsupported benchmark text attribute: {attr}')
    return result
