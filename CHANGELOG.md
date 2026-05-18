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
- Refined Settings labels, hover text, and tooltips so performance notes appear only where settings affect runtime, memory, disk writes, network/API usage, or model behavior.
- Removed the legacy Settings-page LLM glossary and glossary-prompt text editors; project glossaries are edited through the Glossary window and saved in `glossary.json`.
- Expanded LLM and Two-Step Settings hover text with performance effects for provider choice, API keys and rate limits, glossary/context size, reasoning, reflection, JSON mode, delay, per-block translation, refinement batch size, pipeline overlap, and VRAM unloading.
- Drawboard checkbox for showing translated text boxes while mask editing.

### Changed

- Existing translation, OCR, and inpainting workflows are unchanged.
- Review now uses character and honorific glossary entries as guidance.
- Manual glossary entries are preserved and preferred over automatic entries.
- Project glossaries now save to `glossary.json` in the image project folder instead of the global translator config or embedded `imgtrans` project JSON.
- Direct Google/DeepL translation and Two-Step first-step translation now persist raw provider results in each project's `imgtrans_*.json`.
- Dynamic module parameter tooltips now use their module-provided descriptions without appending a generic performance note.
- UI-only settings such as preset import/export, mouse-wheel protection, startup reopening, keyboard shortcuts, and display filters now avoid performance claims.
- LLM translators now read glossary entries and the glossary prompt only from the current project's separate `glossary.json` data.
- Translator hover descriptions now distinguish true speed impacts from reliability, memory-safety, or quota-related behavior.

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
- Bumped the fork runtime version string to `1.4.0-vibe.36`.
- Bumped the fork runtime version string to `1.4.0-vibe.37`.
- Bumped the fork runtime version string to `1.4.0-vibe.38`.
- Bumped the fork runtime version string to `1.4.0-vibe.39`.
- Preserved Re-Inpaint request metadata through the inpaint thread so the current-page completion handler closes the progress dialog.
- Bumped the fork runtime version string to `1.4.0-vibe.40`.
