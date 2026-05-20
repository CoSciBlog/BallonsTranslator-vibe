# Changelog

## Unreleased

### Added

- Direct `.cbz`, `.cbr`, and `.zip` comic archive import from the Open menu, drag-and-drop, recent projects, and `--proj-dir`.
- Archive extraction into regular image project folders with natural page ordering and `archive_import.json` metadata.
- First-use local model downloads for modules with declared downloadable files, so optional models can be fetched when their backend is selected.
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
- Glossary target-term changes now propagate to existing project translations and trigger affected page re-renders.
- Text box context-menu action for merging two or more selected text boxes into one combined text box without changing the inpainted page layer.
- Run-menu LLM review actions for the current page and all non-ignored pages, using the active ChatGPT, LLM_API_Translator, or Two-Step Translator settings.
- Live first-start progress output for Windows batch launchers and Pinokio install/start scripts, including timed heartbeat messages for silent setup commands.
- Live update progress output for Pinokio `update.js` and `launch.py --update`, including Git progress and dependency refresh step labels.
- Tools-menu Model Downloads window for downloading missing or optional local model files on demand.
- Pinokio `test.js` launcher that installs `requirements-test.txt` only for test runs before executing the unittest suite.
- Shared tooltip wrapping for long Settings and module-parameter hover descriptions.
- Glossary import/export actions in the project Glossary window.
- A separate reference-glossary field for importing glossary context from another chapter without replacing the current project glossary.
- Translated-folder glossary template generation with optional subfolder scanning for extracting likely official names, places, organizations, and titles from translated project/text data.
- `Gloss Scan Current Manga` action in the sidebar and Run menu for detecting text, running OCR, and building a reusable project glossary without translation or inpainting.
- Glossary export/import documentation for using a scanned current-manga glossary as a reference glossary in another chapter or manga.
- Live Runtime Manager pip install output so package downloads, CUDA wheel installs, and progress bars are visible during launch and repair.

### Changed

- Automatic first-start model downloads now also skip optional `aot`, PaddleOCR-VL Manga, native PaddleOCR, OneOCR, and Stariver OCR entries. Backends with known downloadable files remain available through `Tools -> Model Downloads`; native PaddleOCR downloads on first use, OneOCR requires manually supplied local files, and Stariver OCR is API-only.
- Existing translation, OCR, and inpainting workflows are unchanged.
- Review now uses character and honorific glossary entries as guidance.
- Manual glossary entries are preserved and preferred over automatic entries.
- Project glossaries now save to `glossary.json` in the image project folder instead of the global translator config or embedded `imgtrans` project JSON.
- Direct Google/DeepL translation and Two-Step first-step translation now persist raw provider results in each project's `imgtrans_*.json`.
- Dynamic module parameter tooltips now use their module-provided descriptions without appending a generic performance note.
- UI-only settings such as preset import/export, mouse-wheel protection, startup reopening, keyboard shortcuts, and display filters now avoid performance claims.
- LLM translators now read glossary entries and the glossary prompt only from the current project's separate `glossary.json` data.
- LLM translators now include reference-glossary entries as secondary guidance and keep explicit project glossary entries as the preferred source when terms conflict.
- Current-manga glossary scans merge detected OCR terms into the project glossary without overwriting existing manual entries.
- NVIDIA runtime profile installs now force-reinstall PyTorch packages from the selected CUDA/CPU wheel index, preventing a CPU Torch wheel from satisfying the Blackwell cu128 profile.
- Translator hover descriptions now distinguish true speed impacts from reliability, memory-safety, or quota-related behavior.
- The optional `flux2-klein` inpainting model is skipped during automatic first-start model downloads and can be downloaded later from `Tools -> Model Downloads`.
- Save image format and quality descriptions now appear only as hover text instead of visible labels.
- Model Downloads now runs downloads from `Download Selected` and `Download All` in a non-modal background window so the main app remains usable.

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
- Bumped the fork runtime version string to `1.4.0-vibe.41`.
- Bumped the fork runtime version string to `1.4.0-vibe.42`.
- Bumped the fork runtime version string to `1.4.0-vibe.43`.
- Bumped the fork runtime version string to `1.4.0-vibe.44`.
- Bumped the fork runtime version string to `1.4.0-vibe.45`.
- Pinned setup tooling to `setuptools==71.1.0` to avoid `PyExecJS` metadata failures with newer setuptools releases.
- Bumped the fork runtime version string to `1.4.0-vibe.46`.
- Bumped the fork runtime version string to `1.4.0-vibe.47`.
- Bumped the fork runtime version string to `1.4.0-vibe.48`.
- Bumped the fork runtime version string to `1.4.0-vibe.49`.
- Bumped the fork runtime version string to `1.4.0-vibe.50`.
- Bumped the fork runtime version string to `1.4.0-vibe.51`.
- Bumped the fork runtime version string to `1.4.0-vibe.52`.
- Bumped the fork runtime version string to `1.4.0-vibe.53`.
