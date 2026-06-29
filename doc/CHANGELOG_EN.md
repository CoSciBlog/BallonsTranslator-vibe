# Changelogs

### 2026-06-29
[v1.4.0-vibe.83] ChatGPT/OpenAI model selector refresh
Added:
1. Added newer OpenAI model choices to `ChatGPT`, `ChatGPT_exp`, `LLM_API_Translator`, and `LLM_API_Translator_2`: `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, and the `gpt-4.1` family.

Changed:
1. Changed the shipped OpenAI defaults to `gpt-5.5` while preserving saved local settings and explicit override-model values.
2. Updated README and changelog documentation.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.83`.

### 2026-06-29
[v1.4.0-vibe.82] Ollama reasoning timeout handling
Added:
1. Added a configurable LLM `request timeout` so slow local Ollama reasoning models can finish long JSON responses.

Changed:
1. Documented remote Ollama endpoint guidance and recommended `max tokens`, `num ctx`, timeout, and review-pass settings for Qwen/Gemma reasoning models.

Fixed:
1. Post-translation LLM review now keeps existing draft translations when an optional review request times out or hits a retryable provider error.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.82`.

### 2026-05-22
[v1.4.0-vibe.65] LLM prompt placeholder tooltips
Added:
1. Added language placeholder support for LLM `system_prompt` and `reflection prompt`: `{source_language}`, `{target_language}`, `{input_language}`, `{output_language}`, `{from_lang}`, and `{to_lang}`.

Changed:
1. Extended Settings hover text for `system_prompt` and `reflection prompt` so users can see which placeholders are available and what the reflection pass receives automatically.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.65`.

[v1.4.0-vibe.64] sidebar and auto layout polish
Added:
1. Added an Auto layout mode that optimizes text boxes while removing inserted translation line breaks from stored translation text.
2. Added `Ctrl+Shift+P` for showing and hiding the page list.
3. Added full language hover text and wider popups for compact source/target language selectors.

Changed:
1. Shortened Search/Replace sidebar button labels and moved details to tooltips so the sidebar no longer resizes around long actions.
2. Improved disabled Auto layout behavior so rendered text boxes keep a wider balloon-based region instead of collapsing to narrow detected text lines.
3. Updated all Qt translation source files and recompiled the `.qm` translation files.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.64`.

[v1.4.0-vibe.63] settings checkbox wrapping
Changed:
1. Rendered Settings checkbox descriptions as wrapping text beside the checkbox instead of unwrapped checkbox captions.
2. Shortened the visible descriptions for General and DL Module options that previously extended beyond the Settings window.
3. Updated all Qt translation source files and recompiled the `.qm` translation files.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.63`.

### 2026-05-20
[v1.4.0-vibe.59] startup without project fix
Fixed:
1. Fixed startup with no project open after grouped import metadata support was added.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.59`.

### 2026-05-20
[v1.4.0-vibe.58] LLM Gloss Scan reference glossary
Added:
1. Added LLM-backed Gloss Scan extraction after text detection and OCR.
2. Gloss Scan now uses the selected `LLM_API_Translator` or `Two-Step Translator` settings, including Ollama/provider, model, endpoint, JSON/reasoning options, category filters, and glossary max-entry limits.
3. Gloss Scan now uses existing official/reference translations in text blocks as target spellings when building a reusable project glossary for export or later chapters.

Changed:
1. Glossary extraction prompts now include the project's reference glossary as supporting context while preserving project glossary entries as preferred terms.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.58`.

### 2026-05-20
[v1.4.0-vibe.57] grouped source folder import
Added:
1. Added source-folder import from `Open -> Import Folder` and drag-and-drop for folders containing `.cbr`, `.cbz`, `.zip`, `.pdf`, and nested image files.
2. Added recursive image-folder import that flattens subfolder images into an ordered image project while ignoring generated project output folders.
3. Added sidebar page labels and tooltips that mark imported pages by source folder, archive, or PDF group.

Changed:
1. Multi-source imports now share the same collection importer for archives, PDFs, and image files.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.57`.

### 2026-05-20
[v1.4.0-vibe.56] PDF comic import
Added:
1. Added direct `.pdf` comic import from the Open menu, drag-and-drop, recent projects, and `--proj-dir`.
2. Added multi-PDF import from the Open menu and drag-and-drop, combining selected PDFs into one ordered image project.

Changed:
1. Documented PDF import support and the PyMuPDF runtime dependency.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.56`.

### 2026-05-20
[v1.4.0-vibe.55] comic archive export
Added:
1. Added comic export for rendered result pages as `.cbz`, `.zip`, `.pdf`, and `.cbr` when a local RAR writer is installed.
2. Added PDF export that writes each rendered image as its own page using that image's dimensions, aspect ratio, and orientation.

Changed:
1. Documented comic archive export, CBR writer requirements, and GPL-3.0 license continuity.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.55`.

### 2026-05-19
[v1.4.0-vibe.50] comic archive import
Added:
1. Added direct `.cbz`, `.cbr`, and `.zip` comic archive import from the Open menu, drag-and-drop, recent projects, and `--proj-dir`.
2. Added archive extraction into regular image project folders with natural page ordering and `archive_import.json` metadata.

Changed:
1. Documented archive import support, CBR `7z` requirements, and GPL-3.0 license continuity.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.50`.

### 2026-05-19
[v1.4.0-vibe.49] settings tooltip cleanup and background model downloads
Added:
1. Added shared tooltip wrapping for long Settings and module-parameter hover descriptions.

Changed:
1. Removed visible description labels from the Save image format and quality controls; the descriptions remain available as hover tooltips.
2. Made the Model Downloads window explicitly non-modal so downloads started with `Download Selected` or `Download All` continue in the background while the main app stays usable.
3. Moved runtime-only Model Downloads notes into item hover text instead of appending them to the visible model row.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.49`.

### 2026-05-19
[v1.4.0-vibe.48] more on-demand model downloads
Added:
1. Added first-use local model downloads for modules that declare downloadable model files.

Changed:
1. Skipped optional `aot`, PaddleOCR-VL Manga, native PaddleOCR, OneOCR, and Stariver OCR entries during automatic first-start model download handling.
2. Kept optional models with known downloadable files available through `Tools -> Model Downloads`.
3. Documented that native PaddleOCR downloads its own runtime assets on first use, OneOCR requires manually supplied local files, and Stariver OCR is API-only.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.48`.

### 2026-05-19
[v1.4.0-vibe.47] lazy test dependencies
Added:
1. Added `requirements-test.txt` for test-only dependency declarations.
2. Added a Pinokio `test.js` launcher that installs `requirements-test.txt` only when tests are run, then executes the unittest suite.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.47`.

### 2026-05-19
[v1.4.0-vibe.46] setup compatibility and on-demand model downloads
Added:
1. Added a `Tools -> Model Downloads` window for downloading selected missing or optional local model files.

Changed:
1. Skipped the large optional `flux2-klein` model during automatic first-start model downloads; common detection, `manga_ocr`, `mit48px`, and LaMa assets still download during setup.
2. Pinned launcher setup tooling to `setuptools==71.1.0` so legacy packages such as `PyExecJS` can generate metadata successfully.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.46`.

### 2026-05-19
[v1.4.0-vibe.45] update progress output
Added:
1. Updated Pinokio `update.js` to show labeled Git and dependency-refresh steps with timed progress heartbeats.
2. Updated `launch.py --update` to stream Git fetch and pull progress while checking and applying fork updates.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.45`.

### 2026-05-19
[v1.4.0-vibe.44] first-start launcher progress output
Added:
1. Added a small launch-step runner that prints timed progress heartbeats while silent setup commands are still running.
2. Updated Windows batch launchers to stream virtual-environment and dependency-install output instead of hiding it in temporary log files.
3. Updated Pinokio install/start scripts to use unbuffered Python output and visible dependency progress.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.44`.

### 2026-05-18
[v1.4.0-vibe.43] Run-menu LLM translation review
Added:
1. Added `Review Current Page` and `Review All Pages` actions to the Run menu.
2. Added a review-only pipeline that re-checks existing translations with the active ChatGPT, LLM_API_Translator, or Two-Step Translator settings without rerunning OCR or inpainting.
3. Review results are applied to text blocks and then re-rendered and saved through the existing page-finish flow.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.43`.

### 2026-05-18
[v1.4.0-vibe.42] text box context merge
Added:
1. Added a right-click text box action for merging two or more selected text boxes into the first selected box.
2. Combined selected source and translated texts with line breaks while preserving the already inpainted page layer and mask data.
3. Added undo/redo support for the merge action and covered merge helper behavior with tests.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.42`.

### 2026-05-18
[v1.4.0-vibe.41] glossary edit propagation
Added:
1. Glossary target-term edits now update matching existing translations and rich text in the open project.
2. Affected pages are re-rendered and saved after glossary replacements are applied.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.41`.

### 2026-05-18
[v1.4.0-vibe.40] re-inpaint completion and drawboard text overlay
Added:
1. Added a Drawboard checkbox for showing translated text boxes while editing or reviewing masks.

Fixed:
1. Preserved current-page Re-Inpaint metadata through the inpaint thread so the completion handler closes the progress dialog after the result is applied.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.40`.

### 2026-05-18
[v1.4.0-vibe.39] translator performance tooltip details
Changed:
1. Expanded LLM_API_Translator hover descriptions for provider latency, API key rate limits, request delay, JSON mode, reasoning, reflection, context pages, glossary prompts, glossary extraction, and low VRAM mode.
2. Expanded Two-Step Translator hover descriptions for parallel first-step translation, refinement batch size, and unloading vision models before local LLM refinement.
3. Clarified that per-text-block translation usually slows translation because it creates more requests.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.39`.

### 2026-05-18
[v1.4.0-vibe.38] project-only glossary settings cleanup
Changed:
1. Removed the legacy LLM glossary and glossary-prompt text editors from Settings.
2. LLM translators now use only the current project's glossary data from `glossary.json` and the Glossary window.
3. Embedded legacy glossary data inside `imgtrans_*.json` is no longer used as a project glossary source.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.38`.

### 2026-05-18
[v1.4.0-vibe.37] settings tooltip cleanup
Changed:
1. Removed the generic module-parameter performance note from Detector, OCR, Inpainter, and Translator settings.
2. Reworded Settings hover descriptions so UI-only controls no longer claim runtime or processing impact.
3. Kept performance notes only on settings that can affect runtime, memory, disk writes, network/API usage, or model behavior.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.37`.

### 2026-05-18
[v1.4.0-vibe.36] settings tooltip reuse and dependency review
Changed:
1. Reused the module-parameter performance tooltip text so labels and controls share one composed tooltip per setting.
2. Reviewed the recent Settings tooltip changes for deprecated Qt/Python patterns; no deprecated API usage was found in the touched code.
3. Checked installed Python packages for available updates and verified `pip check` reports no broken requirements.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.36`.

### 2026-05-18
[v1.4.0-vibe.35] settings performance tooltips
Changed:
1. Expanded Settings labels, hover text, and tooltips with speed, memory, disk-write, cache, API-cost, and quality tradeoff notes.
2. Added a generic performance note to dynamic module parameter tooltips so Detector, OCR, Inpainter, and Translator settings explain likely runtime impact.
3. Updated Qt translation source files and recompiled the `.qm` translation files.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.35`.

### 2026-05-14
[Unreleased] robustness fixes
Changed:
1. Default page zoom now fits the current page into the visible canvas when opening a project.
2. Project glossaries now save to a separate `glossary.json` file in the image project folder.
3. Direct Google/DeepL translation and Two-Step first-step translation now persist raw provider results in each project's `imgtrans_*.json`.

Fixed:
1. Improved handling of malformed or empty LLM JSON responses.
2. Improved Two-Step Translator LLM refinement handling for empty, partial, and malformed JSON responses.
3. Added strict LLM refinement retry before falling back to first-step drafts.
4. Added safe ID-based partial merge for usable LLM refinement outputs.
5. Prevented partial refinement responses from discarding all usable ID-matched translations.
6. Improved Ollama request logging for local translation models.
7. Clarified separation between refinement, strict retry, reflection, and glossary prompts.
8. Improved Windows robustness for atomic project saving and UI save-error handling.
9. Added diagnostics for Censor Restoration mask detection.
10. Improved simple censor bar and block mask detection.
11. Improved auto glossary filtering to avoid classifying interjections, SFX, punctuation, and normal dialogue as character names or titles.
12. Normalized name entries to character glossary category.
13. Added stricter title filtering and glossary rejection diagnostics.
14. Fixed NameError 'np' is not defined during re-inpainting function.
15. Prevented automatically extracted glossary entries from being saved into the global translator config and reused by unrelated projects.

Version:
1. Bumped the fork runtime version string to `1.4.0-vibe.34`.

Added:
1. Optional debug output for Censor Restoration masks and overlays.
2. Manual-mask pipeline fallback support for Censor Restoration integration code.
3. Added LLM model matrix benchmarking for LLM and Two-Step translation.
4. Added repeated benchmark runs per model.
5. Added JSON/CSV benchmark result exports and summary output.
6. Added benchmark metrics for duration, errors, retries, and fallback usage.
7. Added sidebar, Tools-menu, shortcut, and Drawboard controls to re-run inpainting for the current page using existing masks.
8. Saved Google/DeepL provider outputs per text block and showed them in the text editor sidebar for comparison.

[v1.4.0-vibe.28] ui translations and german language
1. Extracted all new strings from recent UI updates and recompiled all `.qm` translation files.
2. Auto-translated missing UI strings for all supported languages using Google Translate.
3. Added German (`de_DE`) and Japanese (`ja_JP`) to the official translation files.
4. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.28`.

[v1.4.0-vibe.27] page panel context menu delete data
1. Added a `Delete Page Data` context menu action to the left-sidebar page list.
2. Wired the action to safely delete textboxes, working masks, and inpainting outputs for the selected page.
3. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.27`.

[v1.4.0-vibe.26] typesetting ui cleanups
1. Removed separate description labels from typesetting settings to reduce clutter.
2. Expanded typesetting configuration descriptions and added them as tooltips to the remaining labels and input fields.
3. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.26`.

[v1.4.0-vibe.25] lama large inpaint mask controls
1. Added `mask_dilation_size`, `mask_dilation_kernel`, and `inpaint_enlarge_ratio` to the `lama_large_512px` Inpainter settings UI.
2. Added hover descriptions for the new LaMa Large mask and crop-context controls.
3. Applied mask dilation and configurable block crop enlargement in the inpainting runtime path.
4. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.25`.

[v1.4.0-vibe.24] translation benchmark and lazy working folders
1. Added a Translation Benchmark window from the Run menu to compare current-page outputs from multiple translators or LLM configurations in a side-by-side table.
2. Kept benchmark translations read-only so comparing outputs does not modify project page text or saved translations.
3. Stopped creating empty `decensor_mask`, `decensored`, and disabled `upscaled` working folders during project load and normal pipeline setup.
4. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.24`.

[v1.4.0-vibe.23] readable source language labels
1. Added English helper names in parentheses to source-language selectors in Settings and the bottom translator bar.
2. Kept translator/config values mapped to the original internal language keys so existing projects and saved configs remain compatible.
3. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.23`.

[v1.4.0-vibe.22] remove decensor UI controls
1. Removed the Decensor section from General settings.
2. Removed the left-sidebar `Decens` button and the Run menu decensor actions.
3. Disabled automatic decensor-after-pipeline triggering during normal runs.
4. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.22`.

[v1.4.0-vibe.21] intermediate image formats and quality
1. Added `JPG` and `WEBP` to the `Intermediate image format` setting.
2. Added a separate intermediate image quality setting independent of final result image quality.
3. Applied intermediate quality to saved masks, inpainted pages, decensor masks, and decensored working images.
4. Updated intermediate image lookup to read existing `JPG`, `JPEG`, and `WEBP` working files.
5. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.21`.

[v1.4.0-vibe.20] real decensor mask detection
1. Removed the fallback that copied normal text/inpaint masks into the `decensor_mask` folder.
2. Expanded automatic decensor mask detection with multi-scale censor-bar detection and more tolerant mosaic-region candidates.
3. Verified the new detector creates non-empty, non-text-mask decensor masks on the reported `holo` sample pages.
4. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.20`.

[v1.4.0-vibe.19] flux2-klein accelerate dependency
1. Added the missing `accelerate>=0.26.0` requirement needed by Diffusers when loading `flux2-klein` GGUF model parameters.
2. Added an early `flux2-klein` dependency check so old environments show a direct update/install hint instead of failing deeper inside Diffusers.
3. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.19`.

[v1.4.0-vibe.18] decensor fallback mask creation
1. Created a fallback decensor mask when automatic decensor detection returns an empty mask.
2. Reused existing project text masks first, then text-box regions, and finally a small centered fallback region.
3. Saved the generated fallback mask to the project `decensor_mask` output before running the selected inpainter.
4. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.18`.

[v1.4.0-vibe.17] current-page decensor worker isolation
1. Prevented current-page and all-pages decensor runs from starting on top of an active pipeline or translation worker.
2. Reused the force-stop cleanup path before decensoring so stuck LLM/background translation work cannot keep touching project state from the wrong thread.
3. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.17`.

[v1.4.0-vibe.16] force stop for stuck runs
1. Added a `Force Stop` button next to the normal run progress `Stop` button.
2. Wired force stop to terminate active pipeline, translator, OCR, text detection, and inpainting threads when a normal stop request is stuck.
3. Reset pipeline stop flags, translation queues, inpainting state, and the progress dialog after a forced stop.
4. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.16`.

[v1.4.0-vibe.15] LLM page context and glossary category filters
1. Added LLM context settings for previous pages, optional next-page context, capped document context pages, and maximum context characters.
2. Injected the context window into both `LLM_API_Translator` and the `Two-Step Translator` LLM refinement prompt.
3. Passed current project/page context from page translation, translation-only runs, full pipeline translation, and text-box right-click translation runs.
4. Added automatic glossary category checkboxes and changed defaults so auto extraction keeps only names and places unless more categories are enabled.
5. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.15`.

[v1.4.0-vibe.14] page pipeline ignore toggle
1. Added page previews to the Pages sidebar list.
2. Added a page context-menu action next to `Reveal in File Explorer` for ignoring or including a page in pipeline runs.
3. Skipped ignored pages during text detection, OCR, translation, and inpainting pipeline runs while keeping manual single-page actions available.
4. Saved ignored page names in each project's `imgtrans_*.json` file under `ignored_pages`.
5. Highlighted ignored pages in the Pages sidebar and bumped the fork runtime version string to `1.4.0-vibe.14`.

[v1.4.0-vibe.13] sidebar decensor current page button
1. Added a left-sidebar `Decens` button below Pages, Search/Replace, and Glossary.
2. Wired the button to the existing current-page decensor pass so only the active page is processed.
3. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.13`.

[v1.4.0-vibe.12] decensor pipeline pass
1. Added a `Decensor` settings section with automatic, green-mask, censor-bar, and mosaic mask modes plus mask dilation and minimum area controls.
2. Added `Decensor Current Page` and `Decensor All Pages` actions to the Run menu.
3. Added an optional `Run decensor pass after pipeline` setting so decensoring can run after normal detection, OCR, translation, and inpainting.
4. Saved generated masks and preview outputs in project-local `decensor_mask` and `decensored` folders, while updating `inpainted` so export uses the decensored image.
5. Reused the selected inpainter for reconstruction, allowing `flux2-klein` to act as an optional decensor/inpainting backend when selected.
6. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.12`.

[v1.4.0-vibe.11] prioritized General settings labels
1. Moved the `Upscaling` and `Post-merge` settings sections to the top of General settings before `Settings presets`.
2. Restored concise visible labels for the upscale factor, maximum long edge, skip threshold, quality preset, and post-merge gap/overlap input fields.
3. Kept the longer field explanations as hover tooltips on both labels and controls.
4. Updated README documentation and bumped the fork runtime version string to `1.4.0-vibe.11`.

### 2026-05-13
[v1.4.0-vibe.10] settings polish and translation-only sidebar run
1. Removed visible labels from the upscale factor, upscale max long edge, skip upscale, upscale quality, and post-merge gap/overlap controls, moving their explanatory text to hover tooltips.
2. Tightened spacing, field height, and margins in the General > Typesetting settings so related controls take less vertical space.
3. Added a glossary icon to the left-sidebar `Gloss` button.
4. Added a second left-sidebar run button, `Trans`, that runs only translation on existing text boxes and skips text detection, OCR, and inpainting.
5. Bumped the fork runtime version string to `1.4.0-vibe.10`.

[v1.4.0-vibe.9] pre-detection page upscaling
1. Added an optional `Upscale pages before detection` setting so projects can create high-resolution working images before text detection runs.
2. Added upscale factor, maximum long-edge resolution, skip-threshold, and speed/quality presets including an `AnimeSharp`-style sharpening mode inspired by 2x-AnimeSharpV4 workflows.
3. Stored upscaled working images in a project-local `upscaled` folder and routed detection, OCR, masks, inpainting, canvas display, and export through those images when present.
4. Ignored generated `upscaled` folders in Git and bumped the fork runtime version string to `1.4.0-vibe.9`.

[v1.4.0-vibe.8] settings input wheel guard and wider fields
1. Added a `Prevent mouse wheel changes on input fields` checkbox in General settings.
2. Added a global UI guard that blocks accidental mouse wheel changes on combo boxes and spin boxes, while forwarding wheel movement to a parent scroll area when possible.
3. Enlarged long parameter fields such as API keys, endpoint URLs, proxy values, glossary prompts, and LLM prompt templates so more text is visible while editing.
4. Bumped the fork runtime version string to `1.4.0-vibe.8`.

[v1.4.0-vibe.7] project glossary UI and persistence
1. Added a left-sidebar `Gloss` button that opens a project glossary window.
2. Saved glossary entries and the custom glossary prompt in each project's `imgtrans_*.json` file.
3. Passed project glossary data into LLM translators and synchronized automatically extracted entries back to the project.
4. Added a custom `glossary prompt` setting and prompt rules that keep metadata such as `[CHARACTER]` or `[PLACE]` out of translated text.
5. Added missing tooltips for common sidebar, title bar, and module selector controls.

[v1.4.0-vibe.6] manga_ocr Transformers compatibility
1. Switched `manga_ocr` from `AutoFeatureExtractor` to `AutoImageProcessor` so the local `data/models/manga-ocr-base` vision model loads under current Transformers releases.
2. Updated the README OCR notes to explain the `Unrecognized feature extractor` failure and the supported image processor path.
3. Bumped the fork runtime version string to `1.4.0-vibe.6`.

[v1.4.0-vibe.5] LLM glossary generation and refinement
1. Added persistent glossary settings to `LLM_API_Translator` for names, places, characters, organizations, titles, and recurring terms.
2. Added automatic glossary extraction after each LLM translation batch so new source/target term pairs can be collected while translating.
3. Added a glossary refinement pass that reruns a translated batch through the LLM and aligns it with the current glossary.
4. Wired the glossary support into the `Two-Step Translator` final LLM refinement step.

[v1.4.0-vibe.4] two-step draft sidebar and request delay
1. Saved the Google/DeepL first-step result on each text block as `translation_draft`.
2. Added a read-only `First step draft` area to the text editor sidebar so the first-step machine translation can be compared with the final LLM-refined translation.
3. Added a `first step delay` setting to throttle Google/DeepL draft requests and reduce the risk of temporary provider blocking.

[v1.4.0-vibe.1] fork documentation and release identity refresh
1. Introduced the fork-aware application version `1.4.0-vibe.1` so this build is clearly distinguishable from upstream `1.4.0`.
2. Replaced the root `README.md` with the English README and refreshed the English documentation for the fork.
3. Documented the Pinokio launcher flow, the shared `./env` virtual environment, and the fork update path to `CoSciBlog/BallonsTranslator-vibe` on `dev`.
4. Recorded that this project is maintained as a Codex-expanded fork with launcher and documentation work layered on top of the upstream desktop app.
5. Added explicit disclosure that translated output and some documentation assets are machine-translated and should be labeled accordingly when republished.

### 2023-04-15
Src download implementation based on gallery-dl (#131) thanks to [ROKOLYT](https://github.com/ROKOLYT)

### 2023-02-27
[v1.3.34](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.34) released
1. fix incorrect orientation assignment for CHT  (#96)
2. convert CHS to CHT if it is required for Caiyun & DeepL (#100)
3. support for webp (#85)

### 2023-02-23
[v1.3.30](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.30) released
1. Migrate to PyQt6 for better text rendering preview and [compatibility](https://github.com/Nuitka/Nuitka/issues/251) with nuitka
2. Support set transparency of text layer (#88)
3. Dump logs to data/logs

### 2023-01-27
[v1.3.26](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.26) released
1. Add support for [saladict](https://saladict.crimx.com) (*All-in-one professional pop-up dictionary and page translator*) in the mini menu on text selection. [Installation guide](doc/saladict.md) 
<img src = "./src/saladict_doc.jpg">

2. Support keyword substitution for OCR & machine translation results [#78](https://github.com/dmMaze/BallonsTranslator/issues/78): Edit -> ```Keyword substitution for machine translation```
3. Support import folder with drag&drop [#77](https://github.com/dmMaze/BallonsTranslator/issues/77)
4. Hide control blocks on start text editing. [#81](https://github.com/dmMaze/BallonsTranslator/issues/81)
5. Bugfix

### 2023-01-08
[v1.3.22](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.22) released
1. Support delete and restore removed text
2. Support reset angle
3. Bugfixes

### 2022-12-31
[v1.3.20](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.20) released
1. Adapted to images with extreme aspect ratio such as webtoons
2. Support paste text to multiple selected Text blocks.
3. Bugfixes
4. OCR/Translate/Inpaint selected text blocks
   lettering style will inherit from corresponding selected block.
   ctc_48px is more recommended for single line text, mangocr for multi-line Japanese, need to retrain detection model make ctc48_px generalize to multi-lines  
   Note that if you use **ctc_48px** make sure that the box is in vertical mode and fits as close to the single line of text as possible
<img src="./src/ocrselected.gif" div align=center>

### 2022-11-29
[v1.3.15](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.15) released
1. Bugfixes
2. Optimize saving logic
3. The shape of Pen/Inpaint tool can be set to rectangle (experimental)

### 2022-10-25
[v1.3.14](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.14) released
1. Bugfixes

### 2022-09-30
Support Dark Mode since v1.3.13: View->Dark Mode

### 2022-09-24
[v1.3.12](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.12) released

1. Support global Search(Ctrl+G) and search current page(Ctrl+F). 
2. Local redo stack of each texteditor are merged into a main text-edit stack, text-edit stack is split from drawing board's now. 
3. Word doc import/export bugfixes
4. Frameless window rework based on https://github.com/zhiyiYo/PyQt-Frameless-Window

### 2022-09-13
[v1.3.8](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.8) released

1. Pen tool bug fixes & optimization
2. Fix scaling
3. Support making font style presets, text graphical effects(shadow & opacity), see https://github.com/dmMaze/BallonsTranslator/pull/38
4. Support word document(*.docx) import/export: https://github.com/dmMaze/BallonsTranslator/pull/40

### 2022-08-31
[v1.3.4](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.4) released

1. Add Sugoi Translator(Japanese-English only, created & authorized by [mingshiba](https://www.patreon.com/mingshiba)): download the [model](https://drive.google.com/drive/folders/1KnDlfUM9zbnYFTo6iCbnBaBKabXfnVJm) converted by [@Snowad14](https://github.com/Snowad14) and put "sugoi_translator" in the "data" folder.
2. Add support for russian, thanks to [bropines](https://github.com/bropines)
3. Support letter spacing adjustment.
4. Vertical type rework & text rendering bug fixes: https://github.com/dmMaze/BallonsTranslator/pull/30

### 2022-08-17
[v1.3.0](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.0) released


1. Fix deepl translator, thanks to [@Snowad14](https://github.com/Snowad14)
2. Fix font size & stroke bug which makes text unreadable
3. Support **global font format** (determine the font format settings used by auto-translation mode): in config panel->Typesetting, change the corresponding option from "decide by the program" to "use global setting" to enable. Note global settings are those formats shown by the right font format panel when you are not editing any textblock in the scene.
4. Add **new inpainting model**: lama-mpe and set it as default.
5. Support multiple textblocks selection & formatting. 
6. Improved manga->English, English->Chinese typesetting (**Auto-layout** in Config panel->Typesetting, enabled by default), it can also be applied to selected text blocks use the option in the right-click menu.

<img src="./src/multisel_autolayout.gif" div align=center>
<p align=center>
batch text formatting & auto layout
</p>

### 2022-05-19
[v1.2.0](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.2.0) released

1. Support DeepL, thanks to [@Snowad14](https://github.com/Snowad14)
2. Add new ocr model from manga-image-translator, support korean recognition
3. Bugfixes

### 2022-04-17

[v1.1.0](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.1.0) released
1. use qthread to write edited images to avoid freezing when turning pages.
2. optimized inpainting policy
3. add rect tool
4. More shortcuts
5. Bugfixes 

### 2022-04-09

1. v1.0.0  released
