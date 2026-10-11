# Glossary system

BallonsTranslator stores a writable `glossary.json` beside every project JSON.
Open **Tools → Glossary Manager** (`Ctrl+Shift+G`) to edit entries, review
automatic suggestions, manage shared sources, resolve conflicts, and configure
automatic extraction. The editor uses the same services as headless translation.

## Files and sources

```text
Manga series/
  series_glossary.json
  Chapter_01/
    imgtrans_Chapter_01.json
    glossary.json
  Chapter_02/
    imgtrans_Chapter_02.json
    glossary.json
```

The project file is writable. A selected series glossary is writable only
through deliberate editor/service actions. Reference glossaries are read-only.
Source paths are stored in `glossary.json` under `metadata.sources`; the project
JSON is unchanged. Relative paths resolve from the chapter directory.

Effective order is confirmed project, confirmed series, confirmed reference,
automatic project, automatic series, automatic reference, and new LLM
suggestions. Different translations for the same normalized term stay visible
in **Conflicts** and are never silently overwritten.

## Editor and settings

**Entries** supports search, filters, CRUD, aliases, notes, review, protection,
JSON import/export, and recovery of missing translations from unambiguous
source/translation pairs already stored in the project's text boxes. **Sources** assigns series/references and copies
confirmed project entries into a series. **Conflicts** copies a chosen decision
into the project glossary. **Settings** persists enablement, extraction and its
categories, translation review, references, series use, warnings, prompt limit,
and manual/automatic confirmation. Defaults preserve existing projects and keep
automatic extraction and confirmation opt-in.

Rule-based extraction keeps a complete translated text-box result when its
source is accepted as a standalone candidate. Candidates without a usable
target stay suggestions even in automatic-confirmation mode. A later pipeline
result may fill an empty confirmed OCR mapping, but never changes an existing
translation, a protected entry, or a rejected suggestion.

## JSON, import, and migration

The schema is [glossary.schema.json](glossary.schema.json). UTF-8 saves use a
same-directory temporary file and atomic replacement. Content signatures stop
one process from overwriting external changes. Invalid files remain untouched.

`GlossaryService.import_file()` accepts the current document. The migration
layer also recognizes 1.4-vibe lines (`source => target [category] # note`) and
simple legacy entry lists. Import reports additions, duplicates, and conflicts.

## Service and future batch API

`GlossaryService` owns one file: `for_project`, `for_path`, lifecycle, CRUD,
search, aliases, review/protection, candidate merge, metadata, import/export.

`GlossaryWorkspace` owns one project context: `assign_series`, `clear_series`,
`add_reference`, `remove_reference`, `source_entries`, `effective_entries`,
`conflicts`, `merge_into_project`, `promote_confirmed_to_series`, `save`,
`reload_external_changes`, `on_project_completed`, and `complete_project`.
All APIs are Qt-free and lock-protected; repository signatures detect competing
writers instead of losing writes.

A future queue should open one workspace per chapter, assign the shared series
file, translate, call `complete_project()`, close, then open the next chapter.
On `GlossaryConflictError`, pause and reload or request a manual merge; never
force-save automatically. A batch queue itself is intentionally not included.
