# Changelogs

### 2026-10-11 — 1.5.19+vibe.26
- Added **Remove Existing Line Breaks...** under **Settings → Typesetting** so previously translated project text can be normalized as well as new pipeline output.
- The explicit project-wide cleanup removes persisted rich-text paragraphs that could restore old hard breaks, creates a project backup, and resets stale undo history after saving.
- Removed the duplicate compact Stroke color picker from the font toolbar; Stroke color remains available in the complete **Text Effect** controls.

### 2026-10-11 — 1.5.19+vibe.25
- Fixed glossary extraction dropping aligned translations solely because the translated text contained punctuation or expanded beyond five words.
- Automatic confirmation now leaves target-less candidates as suggestions, while later successful translations can safely fill confirmed OCR entries that are still empty.
- Added **Fill missing translations** to the Glossary Manager. It recovers empty project entries from unambiguous translated text boxes and skips conflicts, protected entries, rejected suggestions, and existing translations.

### 2026-10-11 — 1.5.19+vibe.24
- Added non-blocking Ollama reasoning-capability detection to each local LLM profile. **Detect** reads the selected model's `/api/show` metadata and displays its reported default.
- Thinking Level now offers only the exact controls advertised by that model, including boolean Enabled/Disabled controls or model-defined named levels; unsupported models are locked to Disabled and missing metadata safely uses Auto.
- Detected controls are persisted per model and use Ollama's native chat request even when the context length remains at the server default. Changing the model or endpoint invalidates stale detected choices.

### 2026-10-11 — 1.5.19+vibe.23
- Fixed the text-style preset context menu inheriting no application theme on Windows, which could leave its frameless popup transparent over the formatting controls.
- The popup now belongs to the preset panel and therefore retains the configured opaque menu background in both light and dark themes.

### 2026-10-11 — 1.5.19+vibe.22
- Added **Two-Step (Google/DeepL + Ollama)** translation: Google Translate, DeepL Free, or DeepL Pro creates the first draft and the selected local Ollama text profile reviews and refines it with the existing context, glossary, retry, and structured-response pipeline.
- Added a dedicated **Settings → Modules → Translator** page for selecting the first-step provider, entering a DeepL key, configuring request delays, and choosing whether a failed Ollama refinement keeps the machine draft.
- Ollama profile selection now remains attached to the two-step translator and filters out incompatible remote profiles. The existing **google** translator remains available as the direct Google-only path without an LLM request.

### 2026-10-11 — 1.5.19+vibe.21
- Redesigned the Ollama memory estimate as a compact themed card placed beside the relevant profile settings instead of an easily clipped sentence below the prompt editor.
- The estimated GiB range, active context length, approximate status, default state, and unavailable state are now visually separated and remain fully explained through a detailed tooltip.

### 2026-10-11 — 1.5.19+vibe.20
- Added opt-in nearby text-box merging under **Settings → Typesetting**, with direction, gap, and overlap controls plus a direct current-page action.
- Successful pipeline runs can now merge only their processed pages; ignored and unselected pages remain untouched, and the existing advanced Region Merge Tool continues to support label rules and whole-project runs.
- Consolidated the shared merge sequence and now preserves both OCR source content and translations while discarding geometry-bound rich text and masks that are invalid after regions are combined.

### 2026-10-11 — 1.5.19+vibe.19
- Added a compact Stroke color picker beside the font-color control in the main text-format toolbar, including English/German tooltips and accessibility text.
- Stroke color changes now use the existing typed effect stack and preserve width, position, opacity, blending, sibling effects, global styles, and multi-selection behavior in one undoable operation.
- Choosing a Stroke color for text without a Stroke explicitly adds the standard Stroke effect, while effect-card edits and undo/redo keep the compact picker synchronized.

### 2026-10-11 — 1.5.19+vibe.18
- Added an opt-in **Remove translation line breaks** setting under **Settings → Typesetting**. New translations can now discard model-authored hard line breaks and rely on the existing text-box layout for automatic wrapping.
- Line-break removal runs after translation conversion, keyword substitution, and letter-case processing; non-CJK lines are joined with one space while CJK lines are joined without artificial spacing.
- Existing projects retain the previous behavior by default, and existing or manually edited translations are never rewritten merely by changing the setting.

### 2026-10-11 — 1.5.19+vibe.17
- Replaced the repository's primary Chinese README with the complete English documentation so the default GitHub and package landing page is now English.
- Updated the language navigation in both English README files to avoid presenting the English main README as a Chinese translation.

### 2026-10-11 — 1.5.19+vibe.16
- Added a persisted translation-failure policy with **Retry once**, **Skip page**, and **Abort pipeline** choices in the Run dialog; the existing skip behavior remains the default.
- Fixed the inpainting CPU fallback to raise `NotImplementedError` correctly, made split `.001`/`.002` download archives extractable with explicit progress, and routed the legacy MIT48px beam entry point through the tensorized decoder cache.
- Made OpenAI Responses transport selectable for deterministic Windows tests, removed sandbox-sensitive temporary-file patterns, and retained the completed Quick Run and Ollama context/RAM controls from the preceding builds.

### 2026-10-10 — 1.5.19+vibe.15
- Added a per-profile local Ollama context length. Explicit values are sent through native `/api/chat` as `options.num_ctx` for translation and vision OCR; `0` preserves Ollama's default behavior.
- Ollama profiles now show a clearly labelled combined RAM/VRAM estimate derived from model-tag parameter count, quantization, and context length without loading a model or accessing the network.
- Standard `:11434/v1`, remote `:11434`, and native `/api/chat` endpoints are supported while retaining JSON Schema, vision input, reasoning control, and token accounting.

### 2026-10-10 — 1.5.19+vibe.14
- Added a separate sidebar quick-run button (`Ctrl+F5`) that starts the pipeline immediately with the current saved module, language, glossary, and processing settings without opening the Run dialog.
- The last Run-dialog page range is now persisted and reused by quick run, with safe defaults and clamping when the next project contains fewer pages.
- The existing `F5` button remains unchanged and continues to open the full Run dialog; the new action has a distinct lightning-marked icon and English/German accessibility text.

### 2026-10-10 — 1.5.19+vibe.13
- Upscaled source images are now renamed with their effective factor, for example `001.png` → `001_x2.png`; another 2× pass produces `001_x4.png`.
- Project page keys, indexes, current-page state, image metadata, and retained text geometry now move atomically with the renamed image, including rollback on activation or save failure.
- Added compatibility with legacy `_upscaled_2x` names and reusable integer-factor naming/scaling support for future x3, x4, and higher workflows.

### 2026-10-10 — 1.5.19+vibe.12
- Added **Tools → Pipeline History** (`Ctrl+Shift+H`) with start time, duration, status, stages, modules, and the LLM profile/model used for translation.
- Normal runs, continue/render operations, re-inpainting, complete batches, and individual batch phases are now recorded in a separate versioned, atomically written `pipeline_history.json`.
- Overall batch records live in the batch root while project phases are also recorded in their project directories; malformed history files are never silently overwritten.

### 2026-10-10 — 1.5.19+vibe.11
- Added **Tools → Re-run Inpainting Current Page/All Pages**, which reruns the selected inpainter from original pages using saved detection masks and text regions instead of compounding old inpainting results.
- Added an optional re-inpainting step to batch processing; it runs after the normal pipeline in per-project mode and remains in the local-model phase in staged mode.
- Re-inpainting respects ignored pages and reuses background cancellation, lazy module loading, project progress persistence, and English/German localization.

### 2026-10-10 — 1.5.19+vibe.10
- Added **Tools → Batch Processing** for processing every image-bearing direct child folder with selectable detector, OCR, fallback OCR, inpainter, translator, glossary scope, and optional 2× source-image upscaling.
- Added complete-project and staged execution plans. Staged mode runs local detector/OCR/inpaint work first, unloads those models, then keeps the translation model available while translating all projects.
- Added safe cancellation, project/glossary persistence, shared batch `series_glossary.json`, Windows completion actions, English/German UI text, and planning/regression tests.

### 2026-10-10 — 1.5.19+vibe.9
- Added dedicated **Text Detector**, **OCR**, and **Inpaint** pages under Settings → Modules. They share the pipeline's selected modules and persisted parameter mappings without loading models when Settings opens.
- Moved glossary behavior controls into a dedicated Modules settings page while keeping entry/source/conflict management in the Glossary Manager.
- Added complete LLM-profile duplication, default automatic source-language selection, persistent per-page pipeline exclusion, and confirmed 2× current-page/project upscaling with source replacement.
- Removed the Sponsor menu entry and added English/German strings plus offscreen and regression coverage for the new settings workflow.

### 2026-10-10 — 1.5.19+vibe.8
- Mouse-wheel input over Settings combo boxes and numeric fields now scrolls the containing settings page instead of changing values accidentally.
- Fixed `ConfigComboBox` scroll-target wiring and applied the same wheel pass-through behavior even when a field has keyboard focus.
- Added an offscreen Qt regression covering focused combo boxes, numeric fields, unchanged values, and continued page scrolling.

### 2026-10-10 — 1.5.19+vibe.7
- Added an opt-in **Unload local models before LLM requests** Pipeline setting that frees BallonsTranslator detector, OCR, translator, and inpainter models before chat, Ollama-compatible, Codex, or image LLM requests.
- LLM pipeline stages now use the existing serial low-VRAM path while the option is enabled, preventing a concurrently used local translation model from being unloaded; released modules still reload lazily when needed.
- Added validated persistence, English/German UI text, request-boundary and memory-release tests, and documentation of the external Ollama-server limitation.

### 2026-10-10 — 1.5.19+vibe.6
- Added the Phase 3 Glossary Manager with searchable CRUD, review/protection controls, JSON exchange, source management, and visible conflict resolution.
- Added reusable series and read-only reference glossaries with deterministic priorities, source tracing, safe persistence, and combined Phase 2 prompt selection.
- Added Qt-free project-context/completion APIs for future batch queues, validated glossary settings, English/German UI strings, schema and documentation, and offscreen/service tests.

### 2026-10-10 — 1.5.19+vibe.5
- Added Phase 2 automatic glossary candidate extraction with atomic deduplication, conflict reporting, review states, and cancellation-safe pipeline integration.
- Added Unicode- and alias-aware selection of confirmed project terms for LLM prompts with configurable entry/token budgets and an optional non-destructive consistency check.
- Preserved external glossary files and every non-glossary translation path; no additional LLM request or dependency is introduced.

### 2026-10-09 — 1.5.19+vibe.4
- Added the Phase 1 project-glossary backend with a versioned Unicode data model and UI-independent CRUD/search service.
- Added standalone atomic `glossary.json` persistence, autosave, external-change protection, import/export, and migration from 1.4-vibe glossaries.
- Integrated glossary creation/loading/closing with the v1.5 project lifecycle without changing project JSON.

### 2026-10-09 — 1.5.19+vibe.3
- Added JPEG and WebP options for intermediate project images.
- Added an independent intermediate-image quality setting and applied it consistently to masks and inpainted images.
- Existing intermediate images are now discovered across PNG, JPEG, WebP, and JPEG XL after changing formats.

### 2026-10-09 — 1.5.19+vibe.2
- Added complete English and German UI catalogs with a selectable German language pack.
- Display translator source and target languages with localized names while preserving stable language identifiers in saved configuration.
- Replaced hard-coded Chinese Region Merge UI text and module parameter labels with translatable English source text.
- Fixed translation extraction in uv virtual environments and added completeness, placeholder, and runtime language-pack tests.

### 2026-10-09 — 1.5.19+vibe.1
- Migrated source checkouts to a uv-managed project runtime: pinned Python, uv, cache, and dependencies now stay under `.runtime` and `.venv` instead of using a global Python installation.
- Existing virtual environments are preserved; incomplete or version-mismatched environments stop with repair guidance instead of being removed automatically.
- Added an early startup error for unsupported Python versions instead of attempting dependency repair on Python 3.13 or newer.

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
