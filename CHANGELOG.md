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

### Changed

- Existing translation, OCR, and inpainting workflows are unchanged.

### Fixed

- Improved Two-Step Translator LLM refinement handling for empty, partial, and malformed JSON responses.
- Added strict LLM refinement retry before falling back to first-step drafts.
- Added safe ID-based partial merge for usable LLM refinement outputs.
- Improved Ollama request logging for local translation models.
- Clarified separation between refinement, strict retry, reflection, and glossary prompts.
