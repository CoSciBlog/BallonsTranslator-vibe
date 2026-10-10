# Glossary implementation progress

## Scope

This document records the completed three-phase glossary work for the v1.5.x
architecture. Phase 3 adds the editor and multi-source workspace while retaining
the Phase 1 service and Phase 2 translation integration. No batch queue is added.

## Architecture

The project glossary is stored as `glossary.json` beside the project's
`imgtrans_*.json`. It is not embedded in the project JSON.

The implementation is split by responsibility:

- `ballontranslator/glossary/models.py` owns immutable entries, documents,
  categories, origins, statuses, and schema constants.
- `ballontranslator/glossary/validation.py` validates and normalizes public
  input while preserving Unicode text.
- `ballontranslator/glossary/migration.py` adapts the line-oriented 1.4-vibe
  payload (`source => target [category] # note`) and simple entry lists to the
  versioned model. It does not import the old UI or term-extraction code.
- `ballontranslator/glossary/persistence.py` owns UTF-8 JSON reads, readable
  serialization, content signatures, external-change detection, and atomic
  same-directory temporary-file replacement.
- `ballontranslator/glossary/service.py` owns CRUD, search, aliases, review
  state, automatic-write protection, duplicate detection, import/export,
  autosave, and source lifecycle.
- `ProjImgTrans` opens or creates the service when a project is loaded and
  closes it when the project/application closes. A broken glossary is reported
  through `glossary_load_error`; the project still opens and the file remains
  byte-for-byte untouched.

The existing v1.5 LLM glossary reader in
`ballontranslator/modules/context/glossary.py` remains the prompt contract for
explicit JSON-array, TXT, and TSV glossaries. Phase 2 adapts selected project
entries to that same contract instead of introducing a parallel prompt path.

Phase 2 is split into three Qt-free responsibilities:

- `ballontranslator/glossary/matching.py` owns Unicode-aware literal matching,
  alias resolution, language filters, and request-local count/token budgets.
- `ballontranslator/glossary/extraction.py` owns conservative rule-based OCR and
  translated-text candidate detection plus validation of optional mock/future
  LLM extraction responses. It never sends a model request.
- `ballontranslator/glossary/integration.py` adapts confirmed entries to the
  existing LLM prompt type, coordinates extraction, and provides a
  non-destructive post-translation consistency check.

The generic translator finalization path stores candidates only after a
successful provider result. `LLMTranslator` selects confirmed project terms
before its immutable request snapshot is created, so provider retries reuse the
same prompt and do not trigger extraction or another LLM call.

Phase 3 adds `glossary/workspace.py` as the UI-independent project context. It
combines the writable project source, an optional writable series source, and
read-only references. `ui/glossary_window.py` is only a client of this layer.
Source assignments live in `glossary.json` metadata, never project JSON.

## Data contract

The document contains `schema_version`, `glossary_id`, `entries`, and optional
`metadata`. Each entry contains:

- `schema_version`, stable `id`, `original`, and `translation`
- `source_language` and `target_language`
- category: Character, Place, Organization, Title, Honorific, Item, Ability,
  Terminology, Catchphrase, or Other
- Unicode aliases and description/notes
- origin: Manual, OCR, LLM, or Import
- status: Suggestion, Confirmed, or Rejected
- `protected`, which blocks automatic edits/deletes while allowing deliberate
  manual changes
- ISO-8601 creation/update timestamps and optional confidence from 0 to 1

## Service interfaces

`GlossaryService.for_project(directory)` opens the project source. The primary
methods are:

- lifecycle: `load`, `save`, `close`, `has_external_changes`,
  `reload_if_changed`
- entries: `create_entry`, `get_entry`, `update_entry`, `delete_entry`, `search`
- aliases/review: `add_alias`, `remove_alias`, `confirm_entry`, `protect_entry`
- integrity: `find_duplicates`, `detect_duplicates`
- exchange: `import_file`, `export_file`

Mutations autosave once by default. No-op edits do not write. A changed file is
never overwritten silently: saving raises `GlossaryConflictError` until the
caller explicitly reloads/discards local changes or performs a forced save.

## Completed Phase 1 functionality

- Standalone, versioned `glossary.json` per project
- Automatic create/load and lifecycle integration
- Unicode-safe model and readable UTF-8 JSON
- CRUD, filtering, alias management, confirmation, and protection
- NFKC/case-insensitive duplicate detection across originals and aliases
- Single-write autosave and atomic replacement
- SHA-256 based external modification detection
- Import/export with duplicate and translation-conflict reporting
- 1.4-vibe migration with prompt metadata preservation
- Safe handling of malformed JSON and unsupported future schemas
- No changes to the project JSON schema

## Completed Phase 2 functionality

- Unicode-aware relevant-term matching with script-sensitive word boundaries
- Alias matching while preserving canonical terms as prompt metadata
- Confirmed-only prompt injection, language filtering, deterministic ordering,
  and configurable entry/token budgets
- Project entries merged into the existing LLM glossary contract; confirmed
  project entries take priority over same-source external mappings
- Independent rule-based extraction for proper names, titles/honorifics,
  places, organizations, abilities, items, and short CJK/Hangul term forms
- Validated JSON parser and protocol extension point for a future separately
  configured extraction LLM, with no model/API dependency in Phase 2
- Atomic candidate merge with alias-aware deduplication, conflict reporting,
  confidence enrichment, and suppression of rejected terms
- Confirmed and protected entries are never changed automatically
- Provider-independent extraction after successful block translation; failures,
  cancellation, and persistence conflicts leave completed translation intact
- Optional consistency checking reports possible confirmed-term misses without
  replacing provider output
- Project glossary can be fully disabled; automatic extraction and post-check
  are separate opt-in settings

Configuration defaults:

- `project_glossary_enabled = true`
- `project_glossary_auto_extract = false`
- `project_glossary_postcheck = false`
- `project_glossary_max_prompt_entries = 32`
- `project_glossary_prompt_token_budget = 1200`

## Completed Phase 3 functionality

- Glossary Manager under **Tools** with table CRUD, aliases, categories,
  search/filtering, review state, protection, origin, import/export, sources,
  and manual conflict resolution.
- Project, series, and read-only reference glossaries with traceable sources.
- Effective priority: confirmed project, confirmed series, confirmed reference,
  automatic project, automatic series/reference, then LLM suggestions.
- Confirmed project terms can be copied deliberately into the series glossary.
- Phase 2 LLM prompt selection consumes the combined effective glossary while
  automatic candidates continue to write only to the project source.
- Qt-free workspace operations for source assignment, effective views, merges,
  conflicts, persistence, external reloads, and project-completion callbacks.
- Settings for enablement, extraction categories, review, references, series,
  warnings, prompt limit, and manual/automatic confirmation.
- English source strings, German translations, JSON Schema, user/service guide,
  and offscreen UI tests.

The token budget uses a conservative UTF-8 serialized-size upper estimate so
selection stays deterministic and offline across providers. A provider-specific
tokenizer is not required.

## Translation integration

1. OCR populates text blocks through the existing OCR workers.
2. The translator reads the already-open project `GlossaryService`.
3. For LLM translation, matching confirmed entries and aliases are selected
   under the configured budgets and frozen in `RequestContext`.
4. Translation runs through the unchanged provider request/retry path.
5. After successful generic block finalization, the independent extractor may
   create or enrich reviewable `Suggestion` entries.
6. The service deduplicates the whole candidate batch under its lock and writes
   at most once. Later pages can use entries after manual confirmation.

No global source or translation replacement is performed. External glossary
files remain supported, and providers other than `LLMTranslator` receive no
prompt changes.

## Comparison with 1.4-vibe

The 1.4-vibe implementation supplied useful category-hint and capitalized-term
ideas, but mixed folder scanning, extraction, formatting, persistence, and UI
state. Phase 2 reimplements only compatible detection concepts behind the Phase
1 model/service boundary. It does not port the old files, line storage, widget,
or project-JSON coupling.

## Changed files

- `ballontranslator/glossary/__init__.py`
- `ballontranslator/glossary/models.py`
- `ballontranslator/glossary/validation.py`
- `ballontranslator/glossary/migration.py`
- `ballontranslator/glossary/persistence.py`
- `ballontranslator/glossary/service.py`
- `ballontranslator/glossary/matching.py`
- `ballontranslator/glossary/extraction.py`
- `ballontranslator/glossary/integration.py`
- `ballontranslator/glossary/workspace.py`
- `ballontranslator/modules/translators/base.py`
- `ballontranslator/modules/translators/trans_llm.py`
- `ballontranslator/utils/config.py`
- `ballontranslator/utils/proj_imgtrans.py`
- `ballontranslator/ui/mainwindow.py`
- `ballontranslator/ui/mainwindowbars.py`
- `ballontranslator/ui/glossary_window.py`
- `tests/test_project_glossary.py`
- `tests/test_glossary_phase2.py`
- `tests/test_glossary_workspace.py`
- `tests/test_glossary_window.py`
- `docs/GLOSSARY.md`, `docs/glossary.schema.json`
- `docs/GLOSSARY_PROGRESS.md`
- `README.md`, `README_EN.md`, `doc/CHANGELOG.md`, `doc/CHANGELOG_EN.md`
- `pyproject.toml`

## Verification

`tests/test_project_glossary.py` covers creation, existing-file loading,
Unicode, CRUD/search, aliases, normalized duplicates, no-op writes,
import/export, conflicts, legacy migration, corrupt/future schemas, protected
automatic operations, atomic replacement, external edits, and project
open/close behavior. The broader project and translation regression commands
and their results are recorded in the completion summary for this phase. The
final targeted run completed 58 backend/project/context/catalog tests, and the
translation integration discovery run completed another 6 tests (64 passed).

`tests/test_glossary_phase2.py` covers Unicode boundaries, aliases, confirmed
priority, language filtering, unknown and ambiguous terms, all requested term
categories, mock-LLM response parsing, prompt integration, count/token budgets,
consecutive pages, atomic parallel deduplication, conflicts, confirmed/protected
and rejected records, disabled/no-glossary operation, non-destructive post-check,
provider failure, and extractor failure.

Phase 2 verification on Windows 11 with the project `.venv`:

- 20 Phase 2 tests passed.
- 48 combined Phase 1, Phase 2, project-lifecycle, and prompt-contract tests
  passed.
- 32 LLM history regression tests passed.
- 14 LLM memory and 14 LLM summary regression tests passed.
- 6 LLM translation integration tests passed.
- In total, 114 targeted tests passed without an LLM API call or GPU.

The broader `test_llm_translat*.py` discovery additionally reaches five legacy
`test_llm_translator.py` cases that import the optional `openai` package; that
package is not installed in the current `.venv`, so those five cases could not
run. Existing Windows-only test limitations remain: three config tests reopen a
live `NamedTemporaryFile`, and one path-expansion test assumes changing `HOME`
changes Windows `expanduser('~')`. These failures predate Phase 2 and are not in
the modified production paths.

## Known limitations

- External edits and parallel writers are detected but not automatically
  three-way merged.
- Legacy target-only preferred terms migrate as identity mappings so their
  spelling is retained; they are used only when confirmed and source-relevant.
- Reference sources are read-only by policy. A chosen reference decision must
  be copied into the project glossary to edit it.
- The built-in extractor is deliberately conservative and does not perform
  semantic named-entity recognition. The Phase 2 protocol/parser prepares a
  separately configured extraction LLM, but no extra model request is made yet.
- Post-check findings are logged and never rewrite translations automatically.

## Recommended next steps

1. Add an explicitly selected extraction profile that implements
   `GlossaryCandidateExtractor`; keep it separate from the translation profile,
   batch requests once, and feed responses through `parse_llm_candidates`.
2. Surface post-check findings inline in translation review without automatic
   replacement.
3. Build a separate batch queue around `GlossaryWorkspace.complete_project()`;
   serialize shared-series writes and pause on `GlossaryConflictError`.
4. Add an optional three-way merge assistant for externally edited glossaries.
