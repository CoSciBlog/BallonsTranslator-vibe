# Changelog

## Unreleased

### Added

- Censor Restoration / Decensor Inpaint pipeline for simple dark or light censor bars.
- Automatic mask detection for block-like censor regions.
- Current-page restoration path using existing inpainting backends.
- Sidebar action for current-page Censor Restoration / Decensor Inpaint.
- General settings for Censor Restoration mask mode, padding, and minimum area ratio.
- Optional debug mask, overlay, and detected-box output.
- Synthetic tests for censor mask detection and the restoration pipeline.
- Added character/name glossary extraction during the first translation pass.
- Added glossary-assisted name consistency checks during translation review.
- Added pronoun and address-form checks to the translation review prompt.
- Saved Google/DeepL provider outputs per text block and showed them in the text editor sidebar for comparison.
- Expanded Settings labels, hover text, and tooltips with performance notes for speed, memory, disk writes, API cost, cache behavior, and module-specific tradeoffs.

### Changed

- Existing translation, OCR, and inpainting workflows are unchanged.
- Review now uses character and honorific glossary entries as guidance.
- Manual glossary entries are preserved and preferred over automatic entries.
- Project glossaries now save to `glossary.json` in the image project folder instead of the global translator config or embedded `imgtrans` project JSON.
- Direct Google/DeepL translation and Two-Step first-step translation now persist raw provider results in each project's `imgtrans_*.json`.
- Dynamic module parameter tooltips now include a general performance note so OCR, detector, translator, and inpaint settings explain likely speed and memory tradeoffs.

### Fixed

- Improved Two-Step Translator LLM refinement handling for empty, partial, and malformed JSON responses.
- Added strict LLM refinement retry before falling back to first-step drafts.
- Added safe ID-based partial merge for usable LLM refinement outputs.
- Prevented partial refinement responses from discarding all usable ID-matched translations.
- Improved Ollama request logging for local translation models.
- Clarified separation between refinement, strict retry, reflection, and glossary prompts.
- Bumped the fork runtime version string to `1.4.0-vibe.29`.
- Reduced inconsistent character names and pronoun drift during review.
- Prevented automatically extracted glossary entries from being carried into unrelated projects through `config/config.json`.
- Bumped the fork runtime version string to `1.4.0-vibe.34`.
- Bumped the fork runtime version string to `1.4.0-vibe.35`.
