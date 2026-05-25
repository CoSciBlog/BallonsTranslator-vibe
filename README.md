> [!IMPORTANT]
> If you share translated pages publicly and no experienced human translator fully translated or proofread them, label the result clearly as machine translation.

> [!NOTE]
> This fork contains machine-translated content in two places: translated comic text produced by the app, and documentation that was machine-translated or normalized for this fork. Portions of this README were consolidated from machine-translated project materials and then edited for consistency.

# BallonsTranslator Vibe Fork
English | [README mirror](/README_EN.md) | [pt-BR](doc/README_PT-BR.md) | [Russian](doc/README_RU.md) | [Japanese](doc/README_JA.md) | [Indonesian](doc/README_ID.md) | [Vietnamese](doc/README_VI.md) | [Korean](doc/README_KO.md) | [Spanish](doc/README_ES.md) | [French](doc/README_FR.md)

Fork release: `1.4.0-vibe.73`
Upstream base: `BallonsTranslator 1.4.0`
Update source: `https://github.com/CoSciBlog/BallonsTranslator-vibe.git` (`dev`)

BallonsTranslator is a desktop tool for comic and manga translation with OCR, text detection, inpainting, translation, and interactive text editing.

This repository is a Codex-expanded fork. It keeps the original desktop workflow, adds Pinokio launcher integration in the project root, documents reproducible local startup paths, and makes the fork identity explicit in the runtime version string.

## What changed in this fork

- Added Pinokio launcher scripts in the project root: `install.js`, `start.js`, `update.js`, `reset.js`, `pinokio.js`, and `pinokio.json`.
- Switched the launcher and Windows helper flow to a shared project virtual environment at `./env` instead of the old bundled `ballontrans_pylibs_win` runtime.
- Pointed the built-in update flow at the `CoSciBlog/BallonsTranslator-vibe` fork on the `dev` branch.
- Introduced a fork-aware application version scheme so this build is distinguishable from upstream releases: `1.4.0-vibe.1`.
- Replaced the mixed-language root `README.md` with the English documentation and refreshed the English README for this fork.
- Documented that translated output and some documentation assets are machine-translated and should be disclosed as such when redistributed.
- Fixed `manga_ocr` startup with current Transformers releases by using the image processor API required by the local `manga-ocr-base` vision model.
- Added a project glossary window, project-level glossary persistence in each project's `glossary.json`, and a custom glossary prompt for LLM translation guidance.
- Added an optional settings safety switch that prevents mouse wheel changes on combo boxes and spin boxes, plus wider input fields for long API keys, URLs, and prompts.
- Added optional pre-detection page upscaling with factor, quality, maximum size, and skip-threshold settings.
- Refined the General settings layout, added a glossary icon, and added a sidebar translation-only run button.
- Moved Upscaling and Post-merge settings to the top of General settings, with visible field labels and detailed hover tooltips.
- Added page-list previews, a page context-menu toggle for ignoring pages in pipeline runs, and project JSON persistence for ignored pages.
- Added a zero-padded current/total page counter beside the active page title in the window header.
- Added LLM project-context settings for previous pages, optional next-page context, capped document context, and narrower automatic glossary category extraction.
- Added a `Force Stop` control to the run progress dialog for terminating stuck pipeline or translation threads.
- Added the missing `accelerate>=0.26.0` dependency required by `flux2-klein` GGUF loading.
- Expanded intermediate image saving to `PNG`, `JPG`, `WEBP`, and `JXL` with a separate quality setting.
- Reintroduced Censor Restoration / Decensor Inpaint controls in General settings and added a current-page sidebar action.
- Added a `Ri` sidebar action, Drawboard Re-Inpaint settings tab, Tools-menu action, and `Ctrl+Shift+I` shortcut to re-run inpainting for the current page with existing masks.
- Added readable English names to source-language selectors, for example `日本語 (Japanese)`, `Deutsch (German)`, and `Polski (Polish)`, while keeping the original internal language values.
- Added a Translation Benchmark window from the Run menu to compare current-page translations from multiple translators or LLM configurations side by side.
- Added an LLM model matrix benchmark for repeated `LLM_API_Translator` and `Two-Step Translator` runs across Ollama-style model lists.
- Added saved Google/DeepL provider result fields to each text block so raw first-step drafts are persisted in the project JSON and shown through the labelled machine-draft field.
- Fixed Two-Step Translator reflection so an enabled review pass receives JSON containing the original source, Google/DeepL draft, and LLM proposal; the sidebar now persists separate machine-draft and LLM-review fields with provenance labels.
- Changed project working folders so `mask`, `inpainted`, `upscaled`, `decensor_mask`, and `decensored` are created only when an output is actually written. Upscaling output is no longer created while upscaling is disabled.
- Exposed `mask_dilation_size`, `mask_dilation_kernel`, and `inpaint_enlarge_ratio` for `lama_large_512px` in the Inpainter settings, with hover tooltips and runtime handling in the LaMa inpaint path.
- Refined Settings hover tooltips so performance notes are shown only for options that affect runtime, memory, disk writes, network/API usage, or model behavior.
- Removed the generic module-parameter performance note so Detector, OCR, Inpainter, and Translator settings use their own specific descriptions.
- Removed the legacy LLM glossary and glossary-prompt text editors from Settings; project terminology now comes only from the project's `glossary.json` via the Glossary window.
- Expanded Settings hover descriptions for LLM and Two-Step translation speed factors, including provider latency, API limits, glossary/context prompt size, reasoning, reflection, JSON mode, per-block translation, batching, pipeline overlap, and VRAM unloading.
- Fixed current-page Re-Inpaint completion so the progress dialog closes after the inpaint result is applied.
- Added a Drawboard checkbox to show translated text boxes while editing or reviewing masks.
- Glossary target-term edits now update matching existing translations, re-render affected pages, and save the updated project.
- Added a right-click text box action that merges two or more selected text boxes into the first selected box while leaving the inpainted page layer unchanged.
- Added Run-menu review actions for the current page and all pages, using the active ChatGPT, LLM_API_Translator, or Two-Step Translator settings to re-check and correct existing translations.
- Added optional inpaint optimization: after normal inpainting, the app can re-detect leftover text on the inpainted page and run a second inpaint pass; the same optimization is available for the current page or all non-ignored pages.
- Added an optional Settings switch to run a post-translation pronoun/address review with LLM-capable translators, and tightened translation, glossary, and review prompts for names, gendered wording, pronouns, and speaker/addressee consistency.
- Stabilized the Search/Replace sidebar width, added `Ctrl+Shift+P` for the page list, added full language hover text in selector popups, and added an Auto layout mode that optimizes boxes without saving inserted translation line breaks.
- Extended LLM Settings hover text for `system_prompt` and `reflection prompt` with supported language placeholders, and enabled `{source_language}`, `{target_language}`, `{input_language}`, `{output_language}`, `{from_lang}`, and `{to_lang}` inside those prompts.
- Improved first-start launcher output so Windows batch and Pinokio install/start flows show live dependency output plus periodic progress messages during silent setup steps.
- Improved the Pinokio and `launch.py --update` update flows so Git and dependency refresh steps stream progress output instead of appearing idle.
- Pinned setup tooling to `setuptools==71.1.0` so legacy packages such as `PyExecJS` install correctly during first setup.
- Added `Tools -> Model Downloads` for downloading missing or optional local models on demand, and moved large optional models such as `flux2-klein`, `aot`, and PaddleOCR-VL Manga out of the automatic first-start download set.
- Added a separate Pinokio test launcher and `requirements-test.txt` so test-only dependencies are installed only when tests are run.
- Added first-use local model downloads for backends that declare downloadable files, so optional models can be fetched when the selected backend is first loaded.
- Cleaned up Save settings so image format and quality explanations stay in hover tooltips instead of visible labels, and wrapped long tooltip text for narrower screens.
- Made the Model Downloads window explicitly non-modal so selected or all downloads continue in the background while the app remains usable.
- Added direct comic archive, PDF, and source-folder import for `.cbz`, `.cbr`, `.zip`, `.pdf`, and nested image folders by extracting, rendering, or copying pages into a normal project folder.
- Added comic export for `.cbz`, `.zip`, `.pdf`, and `.cbr` when a local RAR writer is installed.
- Added GUI batch processing from the Open menu for processing each image subfolder as a separate project with its own `glossary.json`, selectable pipeline modules, optional `.cbz`/`.pdf` export, and an optional quit-on-finish mode.
- Added `Tools -> Upscale Project Images 2x` and `Tools -> Upscale Project Images Using Settings` to replace all eligible source pages with staged `_upscaled_<factor>x` outputs and reload the project with visible progress.
- Added `Tools -> Batch Upscale Folders Using Settings...` to choose a parent directory and upscale every immediate source-image subfolder through the configured settings with the same modal progress, ETA, and Stop controls as the run pipeline.
- Added a sidebar `x2` shortcut for the fixed-factor project upscaling action, using the same quality/limit settings and already-upscaled confirmation as `Tools -> Upscale Project Images 2x`.
- Replaced abbreviated sidebar utility actions with local SVG icons and added a current-page Region Merge shortcut that uses the configured Post-merge thresholds.
- Updated Ollama-backed LLM and Two-Step translation to use native `/api/chat` requests, with `num ctx` controlling the Ollama context window per request.
- Added Ollama per-request terminal speed reporting, LLM/Two-Step `Auto (auto detect)` source selection, bilingual target-language labels, and a Translator-section LLM review/optimization switch.
- Added glossary import/export, reference-glossary support, and a translated-folder glossary template builder for reusing official terminology across chapters.
- Added `Gloss Scan`, a current-manga glossary builder available from the Run menu. It detects text, runs OCR, then uses the selected `LLM_API_Translator` or `Two-Step Translator` settings, including Ollama/provider and glossary category settings, to build an exportable project/reference glossary without inpainting.
- Improved Blackwell/RTX 50xx runtime repair so CUDA PyTorch wheels are force-reinstalled from the cu128 index instead of reusing an already-satisfied CPU Torch package, and runtime package installs now stream live progress output.
- Normal starts now skip dependency and Runtime Manager checks after the first successful runtime setup. Checks run again on first start, `--update`, explicit `--repair-runtime`, or when `BALLOONTRANS_FORCE_RUNTIME_CHECK=1` is set.
- Added global Search/Replace sidebar actions to remove translation line breaks from the current page or from every page in the project.
- Extended Search/Replace with an opt-in `Include glossary` mode for project/reference terms, and made `Replace + Re-render` return to the page where it was started.
- Refreshed the icon-only sidebar utility controls with larger icons, including a book icon for Glossary and an explicit `x2` upscale icon.
- Wrapped long Settings checkbox descriptions so General and DL Module options no longer extend beyond the window or create horizontal scrolling.

## Features

- Fully automated translation workflow:
  - automatic text detection
  - OCR
  - inpainting / text removal
  - machine translation
  - automatic typesetting based on the original balloon layout
- Comic archive import and export:
  - open `.cbz`, `.cbr`, `.zip`, or `.pdf` files from the Open menu, drag-and-drop, or `--proj-dir`
  - import one or more PDF/archive files from the Open menu or by dragging them onto the canvas
  - import a whole folder of `.cbr`, `.cbz`, `.zip`, `.pdf`, and nested image files through `Open -> Import Folder` or drag-and-drop
  - extracts archive pages or renders PDF pages into a regular image project folder next to the source file
  - keeps natural page ordering for nested archive paths, multi-source imports, and nested image folders
  - marks imported pages in the sidebar with their source folder, archive, or PDF group
  - exports rendered result pages as `.cbz`, `.zip`, `.pdf`, or `.cbr`
- Interactive editing workflow:
  - rich text editing
  - search and replace
  - text style presets
  - right-click merge for multiple selected text boxes
  - LLM review for current page or all non-ignored pages from the Run menu
  - import and export for Word documents
- Glossary workflow:
  - use `Gloss Scan Current Manga` to run text detection, OCR, and LLM/Ollama glossary extraction on the current project
  - reuses the selected `LLM_API_Translator` or `Two-Step Translator` provider/model settings and automatic glossary category settings
  - uses existing official/reference translations in text blocks as target spellings when available, otherwise it still extracts source-side OCR terms
  - saves the reusable glossary in the project's `glossary.json` so it can be exported or imported as a reference glossary for other chapters
- Image editing workflow:
  - mask editing
  - inpainting brush style cleanup
  - optional second-pass inpaint optimization for the current page, all non-ignored pages, or full pipeline runs
  - support for long-strip and webtoon-style pages
- Censor Restoration / Decensor Inpaint workflow:
  - works on the currently selected page when invoked by the app workflow
  - automatically builds masks for simple black or white censor bars and block-like censor regions
  - repairs the mask with the configured inpainting backend as a plausible inpaint reconstruction
- Headless automation for batch processing from the command line
- GUI batch processing from `Open -> Batch Processing` for selecting a parent folder and running each immediate image subfolder as its own project
- Multiple OCR, translator, and inpainting backends already wired into the desktop app

### Two-Step Translation Provenance

`Two-Step Translator` now records the stages separately in each text block:

- `translation_draft`: the unedited first-step Google or DeepL machine result.
- `translation_llm_review`: the LLM refinement/review output after comparison to the original source.
- `translation`: the editable output used for typesetting and any subsequent manual changes.

When `reflection` is enabled, the extra review request receives JSON input containing `id`, `source`, and `draft_translation`, together with the prior LLM proposal, and must return only `{"translations":[{"id":...,"translation":"..."}]}`. This keeps the review grounded in source text rather than merely paraphrasing an earlier translation.

## Censor Restoration / Decensor Inpaint

Censor Restoration / Decensor Inpaint works on the currently opened page from the left sidebar `Dc` button. It automatically creates a mask for simple black or white censor bars and block-like censor regions, then repairs that masked area with the existing inpainting backend. The result is a plausible inpaint reconstruction and does not recreate source data.

The detection settings are available under `Settings -> General -> Censor Restoration`. You can choose the mask mode, adjust mask padding, and tune the minimum detected area ratio.

If the app reports `No repair mask found`, enable debug mask output when developing or tune the detector thresholds and area settings. The Censor Restoration pipeline also exposes a manual-mask entry point so an existing repair mask can be used by integration code without relying on automatic detection.

Use this feature only for material where you have the necessary rights. Do not use it for real people, minors, or misleading reconstructions. Output quality depends on the image, detected mask, and selected inpainting backend.

Known limitations:

- Complex mosaic censorship is not detected reliably yet.
- Automatic detection can produce false positives or false negatives.
- Difficult structures can create visible inpainting artifacts.
- Semantic or prompt-based inpainting is not a standard part of this MVP.

## Comic archive import and export

Open `.cbz`, `.cbr`, `.zip`, or `.pdf` files from `Open -> Open Comic Archive/PDF`, drag them onto the canvas, or pass a single source file to `launch.py --proj-dir`. The importer extracts supported image pages or renders PDF pages into a normal project folder next to the source file, for example `Series.cbz` or `Series.pdf` becomes `Series/`, then loads that folder through the existing project workflow. The file dialog and drag-and-drop also accept multiple PDFs, archives, or image files in one import; those pages are combined into one ordered image project folder such as `Chapter 01_import/`.

Use `Open -> Import Folder` or drag a folder onto the canvas to import a whole folder containing `.cbr`, `.cbz`, `.zip`, `.pdf`, or supported image files. Image subfolders are scanned recursively and copied into the generated project, while generated project folders such as `mask`, `inpainted`, `result`, and `upscaled` are ignored. Imported sidebar pages show the source folder, archive, or PDF group in their display text and tooltip.

ZIP and CBZ archives are handled with Python's standard `zipfile` support. CBR archives require a local `7z`-compatible extractor on `PATH`; Pinokio's Windows environment provides `7z`. PDF pages are rendered with PyMuPDF. Nested archive folders, PDF pages, and recursive image folders are flattened into ordered page files such as `0001_page.png`, `0002_page.png`, and an `archive_import.json` file records the source files, imported pages, and sidebar groups.

The importer only writes into the derived project folder. If that folder already contains image pages, it is reused instead of being overwritten.

Use `Open -> Export as Comic Archive/PDF` after saving or running the project to export rendered result pages. `.cbz` and `.zip` are written directly with Python's standard ZIP support. `.pdf` writes one image per PDF page and uses each rendered image's own dimensions, so portrait, landscape, and mixed-size pages keep independent page boxes. `.cbr` export requires a local `rar` or WinRAR command line writer; if none is available, use `.cbz`, `.zip`, or `.pdf`.

Use `Open -> Batch Processing` to enter or select one or more chapter/project folders or parent folders, separated by semicolons or new lines. The dialog lets you choose pipeline modules and source/target languages, retry empty OCR output with a fallback OCR backend, skip already processed pages/projects, permanently upscale and replace originals with the chosen factor/quality/size limits before processing, optionally export each finished project as `.cbz` or `.pdf`, and optionally quit when complete. Generated output folders are ignored. A project-count progress bar remains visible above the per-stage progress bars; `Stop All` cancels the active pipeline and all queued projects.

## Re-Inpaint current page

The left sidebar includes a `Ri` button below `Gloss` and `Dc`. It re-runs inpainting for the currently opened page only, using the page's existing text/manual inpaint mask plus any explicit Censor Restoration mask saved for that same page. Masks from other pages, debug masks, thumbnails, and exported result images are not used.

The same action is available from `Tools -> Re-run Inpainting Current Page` and the `Ctrl+Shift+I` shortcut. The Drawboard has a Re-Inpaint settings tab with the current inpainter selector and a dedicated `Dilate` slider, matching the rectangle repair tool's dilation behavior. Re-Inpaint now keeps the page metadata attached to the inpaint result, so the progress dialog can close when the current-page result finishes. This is useful after changing the inpainting model or editing masks manually.

The Drawboard sidebar also includes a `Show translated text` checkbox. Enable it while drawing masks if you need to see the translated text boxes together with the mask layer.

## Inpaint optimization

Enable `Run -> Enable Inpaint Optimization` to add a second detect-and-inpaint pass after normal inpainting. The optimizer scans the finished inpainted page for leftover text-like regions, merges the residual mask into the page mask, and repairs those regions with the active inpainter.

Use the left sidebar `Opt` button or `Tools -> Optimize Inpainting Current Page` for the currently opened page. Use `Tools -> Optimize Inpainting All Pages` to scan all non-ignored pages after a project is already processed.

The left sidebar also includes an `x2` button for the current project. It performs the same operation as `Tools -> Upscale Project Images 2x`: page images are scaled by factor `2.0`, while quality, maximum long edge and skip threshold are read from the Upscaling settings. If page names already contain `upscaled`, the confirmation dialog appears before processing.

## Pronoun and address review

LLM translation and review prompts now explicitly check names, pronouns, gendered wording, first-person singular/plural, speaker/addressee roles, and formal/informal address. Enable `Settings -> DL Module -> Translator -> Review and optimize translation with LLM` to run an additional LLM review pass after translation for each page, using ChatGPT, `LLM_API_Translator`, or `Two-Step Translator`.

Use `Tools -> Model Downloads` to download optional or missing local models after setup. The first setup still downloads the common text detection, `manga_ocr`, `mit48px`, and LaMa inpainting assets, while optional backends such as `flux2-klein`, `aot`, and PaddleOCR-VL Manga are downloaded only from that window or when a backend with declared downloadable files is first loaded. Native PaddleOCR downloads its own runtime assets on first use, OneOCR still requires the local `oneocr.dll` and `oneocr.onemodel` files to be supplied manually, and Stariver OCR is API-based without a local model download.

## Pinokio launcher

This fork includes Pinokio launcher scripts in the project root.

```bash
# Install dependencies into the project venv at ./env
install.js

# Start BallonsTranslator through the same venv
start.js

# Update from the BallonsTranslator-vibe fork, then refresh dependencies
update.js

# Remove the project venv so it can be recreated
reset.js

# Install test-only dependencies, then run the unittest suite
test.js
```

The launcher update flow tracks `https://github.com/CoSciBlog/BallonsTranslator-vibe.git` on the `dev` branch. `update.js` now prints each Git and dependency-refresh step, streams Git/pip/uv output, and emits timed `still working` progress messages while longer update commands are running. The Windows batch launchers also create and reuse the same `env` virtual environment instead of the old bundled `ballontrans_pylibs_win` runtime. On first start, the launchers print the active setup step, stream pip/download output, and emit periodic `still working` progress messages while silent commands such as virtual-environment creation are running. Runtime Manager package installs inherit the terminal so pip download bars and wheel-install output stay visible. After `.runtime_profile.json` has been created, normal starts skip dependency and Runtime Manager checks; checks run again on `--update`, explicit `--repair-runtime`, or when `BALLOONTRANS_FORCE_RUNTIME_CHECK=1` is set. Runtime setup uses `requirements.txt`; test-only packages belong in `requirements-test.txt` and are installed only by `test.js`.

For NVIDIA Blackwell/RTX 50xx systems, the auto profile uses the PyTorch cu128 wheel index. If the base requirements previously installed a CPU Torch wheel, run `python launch.py --runtime-profile nvidia_blackwell_cu128 --repair-runtime`; the repair path force-reinstalls `torch`, `torchvision`, and `torchaudio` from the CUDA index before the health check.

## OCR notes

`manga_ocr` uses the local model in `data/models/manga-ocr-base`. Current Transformers versions load this vision model through `AutoImageProcessor`; older `AutoFeatureExtractor` loading can fail with `Unrecognized feature extractor` even when `preprocessor_config.json` is present.

## Project glossary

The left sidebar includes a book-icon Glossary button that opens the current project's glossary window. Entries, the glossary prompt, optional reference entries, and the optional reference prompt are saved in a separate `glossary.json` file inside the project's image folder, next to the project's `imgtrans_*.json` file, so each manga/comic project keeps its own terminology. The old Settings-page glossary text boxes are no longer used; edit glossary entries and prompts from the Glossary window. LLM translators use those entries for consistency, but category labels and notes such as `[CHARACTER]` or `[PLACE]` are treated as metadata and are not included in translation output. Automatic glossary extraction defaults to character/name entries and places only; optional translator checkboxes can enable organizations, titles, domain terms, honorifics, or catchphrases when needed. Automatically extracted names are merged without replacing existing manual glossary entries.

Use `Import Glossary` to merge entries from another `glossary.json` into the current editable table. Use `Import Reference` to load another chapter's glossary into the separate reference field; reference entries are included in translation and review prompts as supporting context, while explicit project entries take priority when terms conflict. `Export Glossary` writes the full glossary data, including reference entries, to a JSON file.

`Build From Translated Folder` creates a reference glossary template from a folder that already contains translated project data, exported text/markdown, or existing `glossary.json` files. Enable `Include subfolders` when a volume or series folder contains chapter subfolders. The template builder scans existing translated text, extracts likely character names, places, organizations, and titles, and writes them as reference entries so official English names can guide later chapter translations.

`Gloss Scan` is available as the `GScan` sidebar button and as `Run -> Gloss Scan Current Manga`. It temporarily runs text detection and OCR for the current non-ignored pages, skips inpainting, and then uses the selected `LLM_API_Translator` or `Two-Step Translator` settings to extract glossary entries from OCR text plus any existing official/reference translations in the text blocks. It appends likely names, places, organizations, titles, and terms to the current project's glossary without overwriting existing manual entries. Export that glossary from the Glossary window, then import it as a reference glossary in another manga or chapter when official names should guide later translation work.

When an existing glossary entry's target text is changed, for example a character name is corrected, the app applies that target-term change to existing translations in the project, updates rich text where possible, saves `glossary.json` and the project JSON, and re-renders the affected result pages.

Search/Replace has an `Include glossary` checkbox. When enabled, `Translation` also searches/replaces glossary target terms, `Source` handles source terms, and `All` handles both in the project and reference glossary entry lists. `Replace + Re-render` restores the page that was open when the operation began.

Auto Glossary now extracts names/characters more conservatively: `name` entries are normalized to the `character` category, and interjections, SFX, punctuation, normal dialogue, questions, and commands are filtered so they are not saved as names or titles. Manual glossary entries remain dominant over automatic entries.

## Settings input safety

The General settings page includes `Prevent mouse wheel changes on input fields`. When enabled, mouse wheel events over combo boxes and spin boxes are blocked or forwarded to the surrounding scroll area, so scrolling the settings page does not accidentally change values. Long text fields such as API keys, URLs, proxies, and LLM prompt templates are wider or taller so more content remains visible while editing.

## Settings hover hints

Settings hover text now calls out runtime impact only when an option affects processing. Upscaling, larger masks, debug output, extra LLM context, retries, reflection, glossary extraction, high-quality encoders, cache behavior, batching, GPU selection, provider latency, API rate limits, reasoning, JSON retries, VRAM unloading, output limits, and skipped upscaling can affect speed, memory, disk use, API tokens, quality, stability, or visual matching.

UI-only settings such as preset import/export, keyboard shortcuts, mouse-wheel protection, startup reopening, and display filters now use neutral descriptions without performance claims. Detector, OCR, Inpainter, and Translator parameter hints use only the descriptions provided by each module.

Long checkbox descriptions in Settings are rendered as wrapping text beside the checkbox instead of as unwrapped checkbox captions. This keeps options such as Auto layout, custom fonts, Censor Restoration debug masks, Post-merge, Upscaling, and DL Module cache controls inside the visible Settings pane.

## Source language labels

The source-language selector in Settings and the bottom translator bar now shows English helper names in parentheses for native-language entries. Examples include `日本語 (Japanese)`, `简体中文 (Simplified Chinese)`, `繁體中文 (Traditional Chinese)`, `한국어 (Korean)`, `Tiếng Việt (Vietnamese)`, `русский язык (Russian)`, `Deutsch (German)`, and `Polski (Polish)`. The app still stores and passes the original language key to translators, so existing configs remain compatible.

## Pre-detection upscaling

The General settings page starts with an `Upscaling` section. When `Upscale pages before detection` is enabled, each page can be upscaled into the project-local `upscaled` folder before text detection. Detection, OCR, mask creation, inpainting, canvas display, and export then use that high-resolution working image. The settings include labeled fields for upscale factor, maximum long-edge resolution, a long-edge threshold above which images are skipped, and speed/quality presets from `Fast` through `AnimeSharp`; detailed explanations remain available as hover tooltips.

For permanent source-page replacement, use `Tools -> Upscale Project Images 2x` or `Tools -> Upscale Project Images Using Settings`. The first action forces only the factor to `2.0`; both actions use the configured maximum long edge, skip threshold, and quality preset. The second action also uses the configured factor. Generated page files are staged first and then written beside the original pages with names such as `001_upscaled_2x.png` or `001_upscaled_2_5x.png`; originals are removed only after successful generation, and the project reloads the new page files. If any current page filename already contains `upscaled`, the app asks whether those pages should be processed again or skipped. Existing text-box coordinates are scaled to the replacement image, while stale image-processing progress and generated page outputs are reset for a fresh pipeline run.

Use `Tools -> Batch Upscale Folders Using Settings...` to select a parent folder containing multiple chapter/source-image folders. Each immediate subfolder containing image pages is processed with the configured factor, quality and size limits; generated folders named `mask`, `inpainted`, `result`, `upscaled`, `decensor_mask`, and `decensored` are excluded. The batch run uses the same modal progress placement and ETA/Stop controls as the normal run pipeline. Already marked `_upscaled_` images can be included again or skipped before processing begins.

## Post-merge settings

The General settings page also places `Post-merge` near the top, before settings presets. It keeps concise labels for vertical gap, horizontal gap, and overlap thresholds while retaining the longer behavior descriptions in hover tooltips.

The left sidebar Region Merge icon applies these persisted Post-merge mode, gap, and overlap values to nearby text boxes on the current page. Use `Tools -> Region Merge Tool` when label filters, reading directions, or other advanced dialog-only rules are needed.

## Intermediate image saving

The General settings page lets you choose the intermediate image format for project-local masks, inpainted pages, and other working images. Supported formats are `PNG`, `JPG`, `WEBP`, and `JXL`. Intermediate images have their own quality field, separate from the final result image quality, so cache size and working-image fidelity can be tuned independently.

## Page pipeline ignore

The Pages sidebar now shows page previews for the project list. The centered window title shows the selected position and project size next to the active page name, for example `001/217 pages`. Right-click a page and choose `Ignore Page in Pipeline` to skip that page during text detection, OCR, translation, and inpainting runs. Ignored pages are lightly highlighted in the list and saved in the project's `imgtrans_*.json` file under `ignored_pages`. Use the same context menu entry again to include the page in pipeline runs.

## Translation-only run

The left sidebar includes a second run button labeled `Trans`. It runs only machine translation on the current project text boxes and skips text detection, OCR, and inpainting. This is useful after editing source text or switching translator settings when existing text boxes should be reused.

## Run stop controls

The run progress dialog now has both `Stop` and `Force Stop`. `Stop` requests a graceful stop after the current pipeline step. `Force Stop` terminates the active pipeline, translation, OCR, detection, and inpainting threads and closes the progress dialog when a backend or LLM request does not return to the normal stop path.

## LLM context translation

The `LLM_API_Translator` and `Two-Step Translator` can pass project context into each LLM request. `previous context pages` includes source text and existing translations from earlier pages, `include next context page` adds the next page when text is available, and `document context pages` adds a capped source-text window from the broader project. `context max characters` limits the combined context so smaller models are not overloaded.

These settings improve continuity for names, tone, and references when pages are translated in reading order. They do not change the output mapping: the current page or selected text boxes are still the only items returned in the JSON translation response.

## Two-Step LLM refinement

The `Two-Step Translator` first creates Google, DeepL Free, or DeepL draft translations, then asks the configured LLM to refine those drafts into natural dialogue. The LLM is instructed to treat the machine output as a starting point: it must preserve the source meaning and character voice while repairing literal or stiff phrasing, fluency, tone, and punctuation. `fallback to first step` is the final fallback only: it uses first-step draft translations if the normal LLM refinement and the strict LLM retry both fail.

When `Ollama` is selected, translation, refinement, reflection, and glossary calls use Ollama's native `/api/chat` endpoint. Set `num ctx` in translator settings to pass an explicit `options.num_ctx` context window; leave it at `0` to retain the Ollama server default. Existing saved endpoints ending in `/v1` continue to work and are normalized to the native endpoint.

Each native Ollama request now logs terminal performance metrics in the form `Ollama speed ... prompt=... tkn/s | output=... tkn/s`, together with total and model-load duration. The prompt rate covers processing the request context; the output rate is the generation speed of the translated result.

The strict retry is attempted before the final draft fallback when the LLM returns empty JSON, malformed JSON, a partial response, missing IDs, extra IDs, or a mismatched item count. Usable partial LLM results are merged by numeric ID only, never by list position, so a response for `id: 2` cannot be applied to `id: 1`.

When Google, DeepL Free, or DeepL is used directly or as the Two-Step first step, the raw provider output is saved on each text block in `translation_provider_results` inside the project JSON and mirrored into `translation_draft`. The text editor sidebar shows this Google/DeepL result only as `First step draft`; the separate machine-translation-results field was removed.

For local Ollama models such as `translategemma:12b` or `translategemma:27b`, disabling `reasoning` is usually faster and more stable for JSON output. Use moderate `max tokens` values, typically 2048-4096; values above 8192 are clamped for Ollama refinement requests. Raising `num ctx` permits longer prompt context but increases local memory use. Smaller refinement chunks also improve JSON stability for local models.

For `LLM_API_Translator` and `Two-Step Translator`, the source-language list includes `Auto (auto detect)`. Target-language lists show localized names together with their English meaning, for example `日本語 (Japanese)`.

## LLM model matrix benchmark

The Translation Benchmark window in the Run menu can run an LLM model matrix on the current page. It tests `LLM_API_Translator`, `Two-Step Translator`, or both against multiple models, with repeated runs per model and optional warmup runs. This is useful for local Ollama models such as `translategemma:12b`, `translategemma:27b`, or `qwen3.5:9b`.

Benchmark output is written under `benchmarks/results/` as JSON, CSV, and a Markdown summary. The files include duration, success/failure, errors, request counts, JSON parse errors, retry and fallback counters, model name, provider, translator type, token counts when available, and Two-Step refinement timings when available. API keys are not written to the result files.

The same benchmark can be run from the command line:

```bash
python scripts/benchmark_llm_model_matrix.py --models translategemma:12b,translategemma:27b,qwen3.5:9b --translator-types llm,two_step --runs-per-model 3 --provider Ollama --endpoint http://localhost:11434 --texts "こんにちは||ありがとう"
```

## Programmatic use

BallonsTranslator does not expose a built-in HTTP API, so `curl` is not applicable unless you place a wrapper service in front of it. The supported automation path in this fork is the headless CLI entry point.

### CLI

```bash
python launch.py --headless --exec_dirs "[DIR_1],[DIR_2]"
```

### Python

```python
import subprocess

subprocess.run([
    "python",
    "launch.py",
    "--headless",
    "--exec_dirs",
    "[DIR_1],[DIR_2]",
], check=True)
```

### JavaScript

```javascript
const { spawnSync } = require("node:child_process");

const result = spawnSync("python", [
  "launch.py",
  "--headless",
  "--exec_dirs",
  "[DIR_1],[DIR_2]",
], { stdio: "inherit" });

process.exit(result.status ?? 1);
```

### Curl

```bash
# No built-in HTTP API is exposed by this desktop app.
# Use the headless CLI directly, or add your own wrapper server first.
```

## Installation

### Windows packaged path

If you do not want to install Python and Git manually and you have normal Internet access:

- Download `BallonsTranslator_dev_src_with_gitpython.7z` from the upstream distribution links.
- Extract it.
- Run `launch_win.bat`.

The first start can take several minutes while the `env` virtual environment and Python dependencies are created. The launcher now prints live setup output and timed progress messages, so a quiet terminal still means setup is active unless an error is shown.

The provided packages do not run on Windows 7. Windows 7 users need to install [Python 3.8](https://www.python.org/downloads/release/python-3810/) and run the source code directly.

### Run from source

Install [Python](https://www.python.org/downloads/release/python-31011) `<= 3.12` and [Git](https://git-scm.com/downloads).

```bash
# Clone this fork
git clone https://github.com/CoSciBlog/BallonsTranslator-vibe.git
cd BallonsTranslator-vibe
git checkout dev

# Launch the app
python launch.py

# Update from the fork
python launch.py --update
```

The source update command uses the same fork and branch as the Pinokio updater and now streams Git progress while checking, fetching, and fast-forwarding updates.

The first launch installs Python dependencies and downloads required models automatically. If model downloads fail, download the missing `data` assets manually and place them in the expected paths inside the project.

### Pinokio path

Use the launcher files from the project root when you want a one-click install and run flow inside Pinokio:

1. Run `install.js`
2. Run `start.js`
3. Use `update.js` for fork updates
4. Use `reset.js` to recreate the environment from scratch

## Usage

Recommended flow:

1. Start the application from a terminal so crashes still print useful information.
2. Open settings and choose the translator, source language, and target language.
3. Open a folder that contains comic or manga images, or open a `.cbz`, `.cbr`, or `.zip` comic archive.
4. Click `Run` and wait for detection, OCR, translation, inpainting, and typesetting to finish.
5. Review the translated text manually before publishing or sharing.
6. Export rendered pages as `.cbz`, `.zip`, `.pdf`, or `.cbr` from `Open -> Export as Comic Archive/PDF` when needed.

The app estimates font size, color, outline, angle, direction, and alignment from the source page. You can override those defaults with global or per-block formatting controls.

## Settings export and presets

This fork adds settings management in `Settings -> General -> Settings presets`.

- `Export current settings` writes the active application configuration to a JSON file.
- `Import settings file` loads a JSON configuration immediately and updates the active UI/module choices.
- `Save current as preset` stores the current settings as a named preset under `config/presets`.
- `Preset` lets you choose from multiple saved presets and `Apply preset` loads the selected one.
- `Import preset` copies an external preset JSON into the local preset list.
- `Export selected preset` writes the selected preset to a shareable JSON file.

Settings and presets can include translator endpoints, API keys, prompts, model names, and module options. Treat exported JSON files as sensitive if they contain private credentials.

## Two-step translation acceleration

The `Two-Step Translator` can now overlap its first machine-translation step with the image pipeline. Enable `parallel first step during pipeline` in the translator settings to start Google or DeepL draft translation as soon as OCR has produced text for a page. While later pages continue through OCR and inpainting, those first-step drafts are cached in the background.

The final Ollama/LLM refinement still runs only after detection, OCR, and inpainting have finished. If `unload vision models before llm` is enabled, text detection, OCR, and inpainting models are unloaded before the final LLM calls, freeing RAM/VRAM for a local Ollama or LLM Studio model. This is useful on single-GPU systems where the vision models and LLM compete for the same memory.

The first-step Google/DeepL result is saved per text block as a draft and shown in the text editor sidebar as `First step draft` when available. This makes it possible to compare the raw machine translation with the final LLM-refined result while editing.

Use `first step delay` to throttle the Google/DeepL draft calls. Higher values reduce request bursts and lower the risk of temporary provider blocking, but increase total first-step latency. Set it to `0` when you prefer maximum speed and accept the higher request rate.

## LLM translation glossary

The `LLM_API_Translator` and `Two-Step Translator` include glossary support for names, places, and optional terminology categories.

- Project glossary entries and the glossary prompt are edited from the left-sidebar Glossary window and stored in the current project's `glossary.json` file. Entries use the format `source => target [category] # optional note`.
- `use glossary` injects the glossary into translation prompts so known terms are reused consistently.
- `auto build glossary` asks the LLM to extract reusable glossary entries from each translated batch and append or update them in the current project's `glossary.json`. By default, automatic extraction keeps only names and places, and it filters interjections, SFX, punctuation, and normal dialogue out of name/title categories.
- `Gloss Scan Current Manga` builds glossary candidates from detected OCR text and existing official/reference translations using the selected LLM or Two-Step/Ollama settings, without running normal translation or inpainting.
- `auto glossary names`, `auto glossary places`, and the optional organization/title/term/honorific/catchphrase checkboxes control which categories can be captured automatically.
- `glossary refinement pass` runs a second LLM pass after translation to align the translated batch with the current glossary.
- `review speed mode` retains separate quality passes, combines glossary guidance into reflection for a faster single correction pass, keeps reflection only, or suppresses optional review calls. Automatic glossary extraction remains a separate request when enabled because it creates reusable glossary entries.
- `glossary max entries` limits how many entries are kept so prompts do not grow without bound.
- The review/reflection pass checks pronouns, address forms, and speaker/addressee references when enough context is available.
- Character/name glossary entries and aliases are passed into review so inconsistent names can be normalized to the preferred target form.
- Manual glossary entries have priority over automatic extraction and are not overwritten by new auto entries.

This improves consistency across pages, especially for character names, pronouns, address forms, and locations, but it adds extra LLM/API calls and token usage when automatic extraction or the refinement pass is enabled. The LLM can only verify pronouns and address forms from available source, context, and glossary information; it is instructed not to invent unknown gender, pronoun, relationship, or formality details.

## Headless mode

```bash
python launch.py --headless --exec_dirs "[DIR_1],[DIR_2]"
```

Notes:

- Runtime configuration is loaded from `config/config.json`.
- If the rendered font size is off, specify logical DPI manually with `--ldpi`.
- Headless mode is the supported automation path for batch translation in this fork.

## Machine translation policy

- Translated comic text can be machine translation.
- The README and some fork-maintained documentation were machine-translated or machine-assisted before manual cleanup.
- Do not present machine-translated output as human translation unless a qualified translator reviewed it fully.

## Credits

- Upstream project: [dmMaze/BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)
- AI-modified downstream variant referenced by the project: [thomaswantstobeaskeleton/BallonsTranslator-Pro](https://github.com/thomaswantstobeaskeleton/BallonsTranslator-Pro)
- Fork maintenance, archive import/export, launcher integration, Gloss Scan/reference glossary workflows, and documentation extension: this `BallonsTranslator-vibe` fork
- Archive import uses Python standard-library ZIP handling and the user's locally installed `7z`/Pinokio-provided extractor for CBR files.
- Archive export uses Python standard-library ZIP handling for `.cbz`/`.zip`, Pillow PDF writing for per-image PDF pages, and the user's locally installed `rar`/WinRAR command for `.cbr`.
- Sidebar utility icons in `icons/leftbar_*.svg` are original SVG assets created for this fork; no external icon framework or additional icon license is included.

## License

This fork remains licensed under GPL-3.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE.md). Archive import/export does not add cloud services or a new bundled extractor; CBR import uses the user's local `7z`-compatible tool when available, and CBR export uses the user's local `rar`/WinRAR command when available. Gloss Scan and glossary import/export operate on local project text and JSON files and do not add a new bundled service or third-party license.
