"""Project glossary models, persistence, and Qt-free services."""

from .models import (
    ENTRY_SCHEMA_VERSION,
    GLOSSARY_SCHEMA_VERSION,
    GlossaryCategory,
    GlossaryDocument,
    GlossaryEntry,
    GlossaryOrigin,
    GlossaryStatus,
)
from .extraction import (
    GlossaryCandidate,
    GlossaryCandidateExtractor,
    RuleBasedGlossaryExtractor,
    parse_llm_candidates,
)
from .integration import (
    GlossaryConsistencyIssue,
    check_translation_consistency,
    extract_and_store_candidates,
    merge_prompt_entries,
    project_prompt_entries,
)
from .matching import SelectedGlossaryEntry, select_relevant_entries, term_occurs
from .persistence import (
    GlossaryConflictError,
    GlossaryCorruptError,
    GlossaryLoadResult,
    GlossaryPersistenceError,
    GlossaryRepository,
    UnsupportedGlossarySchemaError,
)
from .service import (
    DuplicateGlossaryEntryError,
    GlossaryCandidateMergeResult,
    GlossaryImportResult,
    GlossaryNotFoundError,
    GlossaryProtectedError,
    GlossaryService,
    GlossaryServiceError,
)
from .validation import GlossaryValidationError
from .workspace import (
    EffectiveGlossaryEntry,
    GlossaryConflict,
    GlossaryMergeResult,
    GlossarySource,
    GlossaryWorkspace,
)

__all__ = [
    'GLOSSARY_SCHEMA_VERSION',
    'ENTRY_SCHEMA_VERSION',
    'DuplicateGlossaryEntryError',
    'GlossaryCandidate',
    'GlossaryCandidateExtractor',
    'GlossaryCandidateMergeResult',
    'GlossaryConsistencyIssue',
    'GlossaryCategory',
    'GlossaryConflictError',
    'GlossaryCorruptError',
    'GlossaryDocument',
    'GlossaryEntry',
    'GlossaryImportResult',
    'GlossaryLoadResult',
    'GlossaryNotFoundError',
    'GlossaryOrigin',
    'GlossaryPersistenceError',
    'GlossaryProtectedError',
    'GlossaryRepository',
    'GlossaryService',
    'GlossaryServiceError',
    'GlossaryStatus',
    'GlossaryValidationError',
    'EffectiveGlossaryEntry',
    'GlossaryConflict',
    'GlossaryMergeResult',
    'GlossarySource',
    'GlossaryWorkspace',
    'RuleBasedGlossaryExtractor',
    'SelectedGlossaryEntry',
    'UnsupportedGlossarySchemaError',
    'check_translation_consistency',
    'extract_and_store_candidates',
    'merge_prompt_entries',
    'parse_llm_candidates',
    'project_prompt_entries',
    'select_relevant_entries',
    'term_occurs',
]
