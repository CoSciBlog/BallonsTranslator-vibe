> [!IMPORTANT]
> If you share translated pages publicly and no experienced human translator fully translated or proofread them, label the result clearly as machine translation.

> [!NOTE]
> This fork contains machine-translated content in two places: translated comic text produced by the app, and documentation that was machine-translated or normalized for this fork. Portions of this README were consolidated from machine-translated project materials and then edited for consistency.

# BallonsTranslator Vibe Fork
English | [README mirror](/README.md) | [pt-BR](doc/README_PT-BR.md) | [Russian](doc/README_RU.md) | [Japanese](doc/README_JA.md) | [Indonesian](doc/README_ID.md) | [Vietnamese](doc/README_VI.md) | [Korean](doc/README_KO.md) | [Spanish](doc/README_ES.md) | [French](doc/README_FR.md)

Fork release: `1.4.0-vibe.31`
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
- Added a project glossary window, project-level glossary persistence in `imgtrans` JSON, and a custom glossary prompt for LLM translation guidance.
- Added an optional settings safety switch that prevents mouse wheel changes on combo boxes and spin boxes, plus wider input fields for long API keys, URLs, and prompts.
- Added optional pre-detection page upscaling with factor, quality, maximum size, and skip-threshold settings.
- Refined the General settings layout, added a glossary icon, and added a sidebar translation-only run button.
- Moved Upscaling and Post-merge settings to the top of General settings, with visible field labels and detailed hover tooltips.
- Added page-list previews, a page context-menu toggle for ignoring pages in pipeline runs, and project JSON persistence for ignored pages.
- Added LLM project-context settings for previous pages, optional next-page context, capped document context, and narrower automatic glossary category extraction.
- Added a `Force Stop` control to the run progress dialog for terminating stuck pipeline or translation threads.
- Added the missing `accelerate>=0.26.0` dependency required by `flux2-klein` GGUF loading.
- Expanded intermediate image saving to `PNG`, `JPG`, `WEBP`, and `JXL` with a separate quality setting.
- Reintroduced Censor Restoration / Decensor Inpaint controls in General settings and added a current-page sidebar action.
- Added a `Ri` sidebar action, Drawboard Re-Inpaint settings tab, Tools-menu action, and `Ctrl+Shift+I` shortcut to re-run inpainting for the current page with existing masks.
- Added readable English names to source-language selectors, for example `日本語 (Japanese)`, `Deutsch (German)`, and `Polski (Polish)`, while keeping the original internal language values.
- Added a Translation Benchmark window from the Run menu to compare current-page translations from multiple translators or LLM configurations side by side.
- Added an LLM model matrix benchmark for repeated `LLM_API_Translator` and `Two-Step Translator` runs across Ollama-style model lists.
- Changed project working folders so `mask`, `inpainted`, `upscaled`, `decensor_mask`, and `decensored` are created only when an output is actually written. Upscaling output is no longer created while upscaling is disabled.
- Exposed `mask_dilation_size`, `mask_dilation_kernel`, and `inpaint_enlarge_ratio` for `lama_large_512px` in the Inpainter settings, with hover tooltips and runtime handling in the LaMa inpaint path.

## Features

- Fully automated translation workflow:
  - automatic text detection
  - OCR
  - inpainting / text removal
  - machine translation
  - automatic typesetting based on the original balloon layout
- Interactive editing workflow:
  - rich text editing
  - search and replace
  - text style presets
  - import and export for Word documents
- Image editing workflow:
  - mask editing
  - inpainting brush style cleanup
  - support for long-strip and webtoon-style pages
- Censor Restoration / Decensor Inpaint workflow:
  - works on the currently selected page when invoked by the app workflow
  - automatically builds masks for simple black or white censor bars and block-like censor regions
  - repairs the mask with the configured inpainting backend as a plausible inpaint reconstruction
- Headless automation for batch processing from the command line
- Multiple OCR, translator, and inpainting backends already wired into the desktop app

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

## Re-Inpaint current page

The left sidebar includes a `Ri` button below `Gloss` and `Dc`. It re-runs inpainting for the currently opened page only, using the page's existing text/manual inpaint mask plus any explicit Censor Restoration mask saved for that same page. Masks from other pages, debug masks, thumbnails, and exported result images are not used.

The same action is available from `Tools -> Re-run Inpainting Current Page` and the `Ctrl+Shift+I` shortcut. The Drawboard has a Re-Inpaint settings tab with the current inpainter selector and a dedicated `Dilate` slider, matching the rectangle repair tool's dilation behavior. This is useful after changing the inpainting model or editing masks manually.

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
```

The launcher update flow tracks `https://github.com/CoSciBlog/BallonsTranslator-vibe.git` on the `dev` branch. The Windows batch launchers also create and reuse the same `env` virtual environment instead of the old bundled `ballontrans_pylibs_win` runtime.

## OCR notes

`manga_ocr` uses the local model in `data/models/manga-ocr-base`. Current Transformers versions load this vision model through `AutoImageProcessor`; older `AutoFeatureExtractor` loading can fail with `Unrecognized feature extractor` even when `preprocessor_config.json` is present.

## Project glossary

The left sidebar includes a `Gloss` button with a glossary icon that opens the current project's glossary window. Entries and the glossary prompt are saved inside the project's `imgtrans_*.json` file under `glossary`, so each manga/comic project can keep its own terminology. LLM translators use those entries for consistency, but category labels and notes such as `[CHARACTER]` or `[PLACE]` are treated as metadata and are not included in translation output. Automatic glossary extraction defaults to character/name entries and places only; optional translator checkboxes can enable organizations, titles, domain terms, honorifics, or catchphrases when needed. Automatically extracted names are merged without replacing existing manual glossary entries.

Auto Glossary now extracts names/characters more conservatively: `name` entries are normalized to the `character` category, and interjections, SFX, punctuation, normal dialogue, questions, and commands are filtered so they are not saved as names or titles. Manual glossary entries remain dominant over automatic entries.

## Settings input safety

The General settings page includes `Prevent mouse wheel changes on input fields`. When enabled, mouse wheel events over combo boxes and spin boxes are blocked or forwarded to the surrounding scroll area, so scrolling the settings page does not accidentally change values. Long text fields such as API keys, URLs, proxies, glossary prompts, and LLM prompt templates are wider or taller so more content remains visible while editing.

## Source language labels

The source-language selector in Settings and the bottom translator bar now shows English helper names in parentheses for native-language entries. Examples include `日本語 (Japanese)`, `简体中文 (Simplified Chinese)`, `繁體中文 (Traditional Chinese)`, `한국어 (Korean)`, `Tiếng Việt (Vietnamese)`, `русский язык (Russian)`, `Deutsch (German)`, and `Polski (Polish)`. The app still stores and passes the original language key to translators, so existing configs remain compatible.

## Pre-detection upscaling

The General settings page starts with an `Upscaling` section. When `Upscale pages before detection` is enabled, each page can be upscaled into the project-local `upscaled` folder before text detection. Detection, OCR, mask creation, inpainting, canvas display, and export then use that high-resolution working image. The settings include labeled fields for upscale factor, maximum long-edge resolution, a long-edge threshold above which images are skipped, and speed/quality presets from `Fast` through `AnimeSharp`; detailed explanations remain available as hover tooltips.

## Post-merge settings

The General settings page also places `Post-merge` near the top, before settings presets. It keeps concise labels for vertical gap, horizontal gap, and overlap thresholds while retaining the longer behavior descriptions in hover tooltips.

## Intermediate image saving

The General settings page lets you choose the intermediate image format for project-local masks, inpainted pages, and other working images. Supported formats are `PNG`, `JPG`, `WEBP`, and `JXL`. Intermediate images have their own quality field, separate from the final result image quality, so cache size and working-image fidelity can be tuned independently.

## Page pipeline ignore

The Pages sidebar now shows page previews for the project list. Right-click a page and choose `Ignore Page in Pipeline` to skip that page during text detection, OCR, translation, and inpainting runs. Ignored pages are lightly highlighted in the list and saved in the project's `imgtrans_*.json` file under `ignored_pages`. Use the same context menu entry again to include the page in pipeline runs.

## Translation-only run

The left sidebar includes a second run button labeled `Trans`. It runs only machine translation on the current project text boxes and skips text detection, OCR, and inpainting. This is useful after editing source text or switching translator settings when existing text boxes should be reused.

## Run stop controls

The run progress dialog now has both `Stop` and `Force Stop`. `Stop` requests a graceful stop after the current pipeline step. `Force Stop` terminates the active pipeline, translation, OCR, detection, and inpainting threads and closes the progress dialog when a backend or LLM request does not return to the normal stop path.

## LLM context translation

The `LLM_API_Translator` and `Two-Step Translator` can pass project context into each LLM request. `previous context pages` includes source text and existing translations from earlier pages, `include next context page` adds the next page when text is available, and `document context pages` adds a capped source-text window from the broader project. `context max characters` limits the combined context so smaller models are not overloaded.

These settings improve continuity for names, tone, and references when pages are translated in reading order. They do not change the output mapping: the current page or selected text boxes are still the only items returned in the JSON translation response.

## Two-Step LLM refinement

The `Two-Step Translator` first creates Google, DeepL Free, or DeepL draft translations, then asks the configured LLM to refine those drafts. `fallback to first step` is the final fallback only: it uses first-step draft translations if the normal LLM refinement and the strict LLM retry both fail.

The strict retry is attempted before the final draft fallback when the LLM returns empty JSON, malformed JSON, a partial response, missing IDs, extra IDs, or a mismatched item count. Usable partial LLM results are merged by numeric ID only, never by list position, so a response for `id: 2` cannot be applied to `id: 1`.

For local Ollama models such as `translategemma:12b` or `translategemma:27b`, disabling `reasoning` is usually faster and more stable for JSON output. Use moderate `max tokens` values, typically 2048-4096; values above 8192 are clamped for Ollama refinement requests. Smaller refinement chunks also improve JSON stability for local models.

## LLM model matrix benchmark

The Translation Benchmark window in the Run menu can run an LLM model matrix on the current page. It tests `LLM_API_Translator`, `Two-Step Translator`, or both against multiple models, with repeated runs per model and optional warmup runs. This is useful for local Ollama models such as `translategemma:12b`, `translategemma:27b`, or `qwen3.5:9b`.

Benchmark output is written under `benchmarks/results/` as JSON, CSV, and a Markdown summary. The files include duration, success/failure, errors, request counts, JSON parse errors, retry and fallback counters, model name, provider, translator type, token counts when available, and Two-Step refinement timings when available. API keys are not written to the result files.

The same benchmark can be run from the command line:

```bash
python scripts/benchmark_llm_model_matrix.py --models translategemma:12b,translategemma:27b,qwen3.5:9b --translator-types llm,two_step --runs-per-model 3 --provider Ollama --endpoint http://localhost:11434/v1 --texts "こんにちは||ありがとう"
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
3. Open a folder that contains comic or manga images.
4. Click `Run` and wait for detection, OCR, translation, inpainting, and typesetting to finish.
5. Review the translated text manually before publishing or sharing.

The app estimates font size, color, outline, angle, direction, and alignment from the source page. You can override those defaults with global or per-block formatting controls.

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
- Fork maintenance and launcher/documentation extension: this `BallonsTranslator-vibe` fork

## License

See [LICENSE](LICENSE).
