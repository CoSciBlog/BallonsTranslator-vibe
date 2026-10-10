<p align="center">
  <img
    width="256"
    alt="Spinning fox animation"
    src="https://github.com/user-attachments/assets/fe44e9a6-c7da-4bc5-8421-87fd6c38a0ba"
  />
</p>

<h1 align="center">BallonsTranslator</h1>

<p align="center">Yet another computer-aided comic/manga translation tool powered by deep learning.</p>

<p align="center">
  English | <a href="/doc/README_RU.md">Русский</a> | <a href="/doc/README_JA.md">日本語</a> | <a href="/doc/README_ES.md">Español</a> | <a href="/doc/README_FR.md">Français</a> | <a href="/doc/README_PT-BR.md">pt-BR</a> | <a href="/doc/README_KO.md">한국어</a> | <a href="/doc/README_ID.md">Indonesia</a> | <a href="/doc/README_VI.md">Tiếng Việt</a>
</p>

<p align="center">
  <a href="https://t.me/BallonTranslatorforum"><img src="https://img.shields.io/badge/Telegram-Discussion%20Group-26A5E4?style=flat-square&logo=telegram&logoColor=white" style="vertical-align: middle;" alt="Telegram Group"/></a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <span style="vertical-align: middle;"><b>QQ Group:</b> <code>719881337</code></span>
</p>

# Features
> [!IMPORTANT]
> **If you're sharing the translated result publicly and no experienced human translator participated in a throughout translating or proofreading, please mark it as machine translation somewhere clear to see.**

* Fully automated translation
  - Support automatic text-detection, recognition, removal, and translation. Overall performance is dependent upon these modules.
  - Typesetting is based on the formatting estimation of the original text.
  - Works decently with manga and comics.
  - Improved manga->English, English->Chinese typesetting (based on the extraction of balloon regions.).
  
* Image editing
  - Support mask editing & inpainting (something like spot healing brush tool in PS)
  - Adapted to images with extreme aspect ratio such as webtoons
  
* Text editing
  - Supports WYSIWYG rich-text editing and [text style presets](https://github.com/dmMaze/BallonsTranslator/pull/311)
  - Supports a rich set of [text effects](https://github.com/dmMaze/BallonsTranslator/pull/1296) and [text transforms](https://github.com/dmMaze/BallonsTranslator/pull/1238)
  - Supports find and replace across all text, source text, or translations, and Word document import/export
  - Enable **Remove translation line breaks** under **Settings → Typesetting** to replace translator-authored line breaks in new translations and let each text box wrap the result automatically. The option is disabled by default and does not alter existing or manually edited text.

* User interface localization
  - Complete English and German UI catalogs; choose **Deutsch** from **View → Display Language**.
  - Translator source and target languages use localized display names without changing the identifiers stored in projects and configuration.

* Configurable intermediate images
  - Save masks and inpainted project images as PNG, JPEG, WebP, or JPEG XL with an independent quality setting.

* Low-memory LLM handoff
  - Enable **Unload local models before LLM requests** under **Settings → Pipeline** to release loaded detector, OCR, translator, and inpainter models before an LLM or Ollama request. This makes more RAM and VRAM available to the LLM; released modules load again automatically when needed.
  - The option serializes LLM pipeline stages with local translation to prevent an in-use model from being unloaded. It releases models owned by BallonsTranslator, but cannot unload a model managed by an external Ollama server.
  - Local Ollama profiles expose **Ollama Context Length**. A value above `0` uses Ollama's native `/api/chat` request with `options.num_ctx`; `0` keeps the server default. The profile also shows a deliberately approximate combined RAM/VRAM range when the parameter count can be inferred from a model tag such as `27b-q4_K_M`. Actual RAM/VRAM allocation depends on the model architecture, quantization, GPU offloading, and parallel requests.

* Safer settings scrolling
  - Scrolling the mouse wheel over combo boxes or numeric fields in **Settings** now scrolls the surrounding page without changing the selected value. Values remain editable by clicking, typing, or using the keyboard.

* Integrated module settings and page workflow
  - **Settings → Modules** now includes dedicated **Text Detector**, **OCR**, **Inpaint**, and **Glossary** pages. Detector/OCR/inpainter pages edit the same selected-module parameters used by the pipeline, without loading models merely by opening Settings.
  - LLM profiles can be duplicated with all settings, and **Auto** is the default source-language choice for compatible translators.
  - Use the regular sidebar Run button (`F5`) to review or change pipeline options. The adjacent lightning-marked quick-run button (`Ctrl+F5`) immediately reuses the saved options and last page range.
  - Pages can be excluded from every pipeline stage through **Ignore page** in the thumbnail context menu. Use **Tools → Upscaling → Upscale Current Page / Entire Project 2x** to replace confirmed source images with 2× upscaled copies. Upscaled files carry their effective factor (`001_x2.png`, then `001_x4.png` after another 2× pass), while project page references and metadata are updated with the rename.
  - **On translation error** in the Run dialog can retry a failed page once, skip it, or abort the remaining pipeline. Skip remains the compatibility default.

* Batch processing
  - Open **Tools → Batch Processing** (`Ctrl+Shift+B`) and select a parent folder to process its image-bearing direct child folders sequentially. Detector, primary/fallback OCR, inpainter, translator, glossary scope, and optional pre-upscaling are selectable per run.
  - Choose complete-project order or run detector/OCR/inpaint for every project first, unload local models, and then translate every project while keeping the LLM available. On successful completion the app can do nothing, close, hibernate, shut down, or restart Windows.
  - An optional re-inpainting step runs the selected inpainter again from the original pages using saved detection masks and text regions. The same operation is available for the current page or all pages under **Tools** (`Ctrl+Shift+I` for the current page).

* Pipeline history
  - **Tools → Pipeline History** (`Ctrl+Shift+H`) shows start time, duration, status, stages, modules, and the LLM profile/model used for translation.
  - Normal runs, continue/render operations, re-inpainting, complete batches, and individual batch phases are atomically stored in a separate `pipeline_history.json`.

* Project glossary backend
  - Each project owns a versioned, Unicode-safe `glossary.json` with atomic autosave, migration from 1.4-vibe, duplicate detection, import/export, and a UI-independent service API.
  - Confirmed project entries are selected by Unicode-aware source matching and supplied to LLM translation under configurable entry and token budgets. Aliases are matched without rewriting source text.
  - Optional rule-based extraction records conservative OCR/translation candidates as reviewable suggestions. It never overwrites confirmed, protected, or rejected entries. The feature is controlled by `project_glossary_enabled`, `project_glossary_auto_extract`, and `project_glossary_postcheck` in module configuration.
  - Open **Tools → Glossary Manager** (`Ctrl+Shift+G`) for searchable entry editing, aliases/categories, review and protection, JSON import/export, sources, and conflict resolution. Glossary behavior is configured under **Settings → Modules → Glossary**.
  - Projects can combine their glossary with a shared writable `series_glossary.json` and read-only reference glossaries. Confirmed project decisions have highest priority and confirmed entries can be copied into the series for later chapters.
  - See [Glossary system](docs/GLOSSARY.md) for the JSON schema, 1.4-vibe migration, source priority, service API, and future batch integration.

* <details>
  <summary><i>Context-aware LLM translation & Glossary</i></summary>

  **Translation history**

  - Set **LLM Context** to **+history** to show `LLMTranslator` examples from earlier completed pages. This can keep names, terminology, and tone more consistent. Continue and selected-range runs can also use eligible earlier pages.
  - **Token budget** controls how much earlier translated text is included. Newer pages are kept first. The current page, instructions, glossary, and generated reply need additional space. The default is `10000`.
  - A larger budget gives the model more story context and drops old pages less often, but sends more input and may take longer. Local models may also need substantially more RAM/VRAM. Mainstream providers with large context windows, such as DeepSeek, can often use a higher limit. About 70% of the model's context limit is a reasonable upper bound (`90000` for a 128K model).
  - The history budget also affects prompt caching. While history grows within the budget, consecutive requests keep the same beginning; OpenAI and DeepSeek can reuse these input tokens at a discount and may respond faster. Dropping old pages changes the beginning and resets the cache. A larger budget means fewer resets but sends more history, so it is not guaranteed to cost less.

  The table below is a rough manga-page example using DeepSeek, where cached input tokens cost 10% of regular input tokens. Actual results vary by project, model, and provider.

  | Token budget | Estimated history kept (pages) | Estimated total cost vs. no history |
  |---:|---:|---:|
  | `2048` | 3–4 | 1.65× |
  | `4096` | 6–9 | 1.79× |
  | `8192` | 12–19 | 2.10× |
  | `16384` | 23–38 | 2.66× |

  **Reusable glossaries**

  - Set **Glossary File** in the Run dialog to a UTF-8 `.json`, `.txt`, or `.tsv` file. The file is read-only and can be reused across projects.
  - **Matching** sends only entries whose source terms occur on the relevant page. **All** sends every entry and may use considerably more tokens.
  - Supported formats include:

    ```text
    # Sakura-style text
    source->translation # optional note

    # Tab-separated text
    source<TAB>translation<TAB>optional note
    ```

    ```json
    [
      {"src": "source", "dst": "translation", "info": "optional note"}
    ]
    ```

  - Matching is case-insensitive and literal. Conflicting entries, malformed files, unsupported formats, and missing files stop the translation before an LLM request is sent.
  - Prior-page context and glossary injection affect only `LLMTranslator`; other translators ignore these settings.
  - The standalone **Glossary File** remains supported. Confirmed entries from the current project's `glossary.json` take priority when both sources contain the same term.

  </details>

* <details>
  <summary><i>LLM translation with visual context, page summaries, and a project summary</i></summary>

  **Vision**

  When enabled, models with vision support can use images as context for translation.

  **Summaries and memory**

  Each page summary briefly records details relevant to translation, including characters and relationships, the setting, key events, speaker clues, and unresolved references. Memory is a condensed record of the whole project built from accumulated page summaries. When older summaries no longer fit within the context budget, or when the last page finishes processing, the program sends a separate text-only request to merge those summaries into the existing memory. Subsequent translations reuse this condensed record as stable context.

  </details>

# Installation

## On Windows

**Method A (One-Click Local Environment Setup, requires PowerShell)**:
The script installs `BallonsTranslator` in the directory where you run it:
```powershell
irm https://raw.githubusercontent.com/CoSciBlog/BallonsTranslator-vibe/1.5-vibe/scripts/install.ps1 | iex
```
Or run the following command in the Command Prompt (`cmd.exe`):
```cmd
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/CoSciBlog/BallonsTranslator-vibe/1.5-vibe/scripts/install.ps1 | iex"
```


**Method B (Download Pre-configured Package)**:
Download `Ballonstranslator_win_minium.zip` from [GitHub Releases](https://github.com/dmMaze/BallonsTranslator/releases), extract it, and double-click `launch_win.bat` to launch the application.

When `launch_win.bat` is run from a source checkout, it bootstraps uv into `.runtime/uv`, lets uv install the pinned Python version from `.python-version` into `.runtime/python`, and creates an isolated `.venv`. The uv cache also stays under `.runtime`. Neither a global Python nor a global uv installation is used. Existing virtual environments are never deleted automatically; an incomplete or mismatched `.venv` is preserved and reported with repair instructions.

These methods do not support Windows 7; Windows 7 users must install [Python 3.8](https://www.python.org/downloads/release/python-3810/) manually and run from source.

If you see errors involving `msvcp140.dll`, `c10.dll`, or `[WinError 1114]`, install or update the [Microsoft Visual C++ Redistributable x64](https://aka.ms/vc14/vc_redist.x64.exe) (Visual Studio 2015-2022; [official download notes](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)).

## macOS / Linux

The script installs `BallonsTranslator` in the directory where you run it:
```bash
curl -fLO https://raw.githubusercontent.com/CoSciBlog/BallonsTranslator-vibe/1.5-vibe/scripts/install.sh && chmod +x install.sh && ./install.sh
```

If `curl` is not available, download the script with `wget -O ...` instead. The app launches automatically after installation; later, use `cd BallonsTranslator && ./launch.sh` to start it again.

The app checks core dependencies at startup. When you select a module that needs extra libraries, the app will prompt you to install the missing optional dependencies (you can also enable automatic installation in Settings).


# Usage

**It is recommended to run the program in a terminal in case it crashed and left no information, see the following gif.**
<img src="https://github.com/user-attachments/assets/ee92fbdc-718c-4e04-a876-0eff3ee2a989">
- The first time you run the application, please select the translator and set the source and target languages by clicking the settings icon.
- Open a folder containing images of a comic (manga/manhua/manhwa) that need translation by clicking the folder icon.
- Click the `Run` button and wait for the process to complete.

The font formats such as font size and color are determined by the program automatically in this process, you can predetermine those formats by change corresponding options from "decide by program" to "use global setting" in the config panel->Typesetting. (global settings are those formats shown by the right font format panel when you are not editing any textblock in the scene)
<img src="https://github.com/user-attachments/assets/fb8a8b2c-54e4-4579-8319-42a172296c80">

## Image Editing

### Inpaint Tool
<img src="https://github.com/user-attachments/assets/de0bc35d-6651-4f2f-985c-cfe9bfafb124">
<p align = "center">
Image Editing Mode, Inpainting Tool
</p>

### rect tool
<img src="https://github.com/user-attachments/assets/6c47f46f-ffd3-41fd-b667-5442be304c79">
<p align = "center">
Rect Tool
</p>

To 'erase' unwanted inpainted results, use the inpainting tool or rect tool with your **right button** pressed.
The result depends on how accurately the algorithm ("method 1" and "method 2" in the gif) extracts the text mask. It could perform worse on complex text & background.

## Text editing
<img src="https://github.com/user-attachments/assets/0f688abe-41f7-416a-85c8-e0dd6968fd00">
<p align = "center">
Text Editing Mode
</p>

<img src="https://github.com/user-attachments/assets/6d31c8a5-b909-4339-8036-7fc3ba2f014c" div align=center>
<p align=center>
Batch Text Formatting & Auto Layout
</p>

<img src="https://github.com/user-attachments/assets/1b76c164-1454-4aa7-b60c-9fbdb0968350" div align=center>
<p align=center>
OCR & Translate Selected Area
</p>

## Shortcuts
* ```A```/```D``` or ```pageUp```/```Down``` to turn the page
* ```Ctrl+Z```, ```Ctrl+Shift+Z``` to undo/redo most operations. (note the undo stack will be cleared after you turn the page)
* ```T``` to text-editting mode (or the "T" button on the bottom toolbar).
* ```W``` to activate text block creating mode, then drag the mouse on the canvas with the right button clicked to add a new text block. (see the text editing gif)
* ```P``` to image-editting mode.
* In the image editing mode, use the slider on the right bottom to control the original image transparency.
* Disable or enable any automatic modules via titlebar->run, run with all modules disabled will re-letter and re-render all text according to corresponding settings.
* Set parameters of automatic modules in the config panel.
* ```Ctrl++```/```Ctrl+-``` (Also ```Ctrl+Shift+=```) to resize image.
* ```Ctrl+G```/```Ctrl+F``` to search globally/in current page.
* ```0-9``` to adjust opacity of text layer
* For text editing: bold - ```Ctrl+B```, underline - ```Ctrl+U```, Italics - ```Ctrl+I```
* Set text shadow and transparency in the text style panel -> Effect.
* ```Alt+Arrow Keys``` or ```Alt+WASD``` (```pageDown``` or ```pageUp``` while in text editing mode) to switch between text blocks.

<img src="https://github.com/user-attachments/assets/084a250d-6a31-4344-94c0-2a5f4ba64b96">

## Headless mode (Run without GUI)
``` python
python -m ballontranslator --headless --exec_dirs "[DIR_1],[DIR_2]..."
```
Note the configuration (source language, target language, inpaint model, etc) will load from config/config.json.
If the rendered font size is not right, specify logical DPI manually via ```--ldpi ```, typical values are 96 and 72.


# Automation modules
This project is heavily dependent upon [manga-image-translator](https://github.com/zyddnys/manga-image-translator), online service and model training is not cheap, please consider to donate the project:
- Ko-fi: <https://ko-fi.com/voilelabs>
- Patreon: <https://www.patreon.com/voilelabs>
- Afdian: <https://afdian.net/@voilelabs>

[Sugoi translator](https://sugoitranslator.com/) is created by [mingshiba](https://www.patreon.com/mingshiba).
  
## Text detection
 * Support English and Japanese text detection, training code and more details can be found at [comic-text-detector](https://github.com/dmMaze/comic-text-detector)
 * Support using text detection from [Starriver Cloud (Tuanzi Manga OCR)](https://cloud.stariver.org.cn/). Username and password need to be filled in, and automatic login will be performed each time the program is launched.

   * Detailed Tuanzi OCR instructions are currently available in [Chinese](doc/团子OCR说明.md).

 * `YSGDetector` models are trained by [lhj5426](https://github.com/lhj5426), these models would filter out onomatopoeia in CGs/Manga, download checkpoints from [YSGYoloDetector](https://huggingface.co/YSGforMTL/YSGYoloDetector) and put into `data/models`.


## OCR
 * All mit* models are from manga-image-translator, support English, Japanese and Korean recognition and text color extraction.
 * [manga_ocr](https://github.com/kha-white/manga-ocr) is from [kha-white](https://github.com/kha-white), text recognition for Japanese, with the main focus being Japanese manga.
 * [PaddleOCRVLManga](https://huggingface.co/jzhang533/PaddleOCR-VL-For-Manga) finetuned on Japanese manga
 * Support using OCR from [Starriver Cloud (Tuanzi Manga OCR)](https://cloud.stariver.org.cn/). Username and password need to be filled in, and automatic login will be performed each time the program is launched.
   * The current implementation uses OCR on each textblock individually, resulting in slower speed and no significant improvement in accuracy. It is not recommended. If needed, please use the Tuanzi Detector instead.
   * When using the Tuanzi Detector for text detection, it is recommended to set OCR to none_ocr to directly read the text, saving time and reducing the number of requests.
   * Detailed Tuanzi OCR instructions are currently available in [Chinese](doc/团子OCR说明.md).
* Added as an "optional" PaddleOCR module. In Debug mode you will see a message stating that it is not there. You can simply install it by following the instructions described there. If you don’t want to install the package yourself, just uncomment (remove the `#`) the lines with paddlepaddle(gpu) and paddleocr. Bet everything at your own peril andrisk. For me (bropines) and two testers, everything was installed fine, you may have an error. Write about it in issue and tag me.
* Added [OneOCR](https://github.com/b1tg/win11-oneocr). Local WINDOWS model taken from SnippingTOOL or Win.PHOTOS applications. To use it, you need to place the model and DLL files in the 'data/models/one-ocr' folder. Before running, it is better to throw the files at once. Read how to find and get DLL and model files here: https://github.com/dmMaze/BallonsTranslator/discussions/859#discussioncomment-12876757 . Thanks AuroraWright for the project [OneOCR](https://github.com/AuroraWright/oneocr)
 * OCR setting: Font recognition. Download the [Font Recognition Model (YuzuMarker.FontDetection)](https://github.com/JeffersonQin/YuzuMarker.FontDetection) and place it in the data\models\YuzuMarker.FontDetection directory.
  The three required files are: `data\models\YuzuMarker.FontDetection\font_dataset`, `data\models\YuzuMarker.FontDetection\name=4x-epoch=18-step=368676.ckpt`, and `data\font_demo_cache.bin`
  Font names with a recognition confidence rate greater than 60% will be saved in the `_detected_font_name` field of the JSON file. Currently, no visual display is provided. When exporting LabelPlus txt using the script [scripts/BTjson_to_LPtxt.pyw], you can optionally include font and font size information for importing into other software (such as Photoshop/InDesign) for text embedding.

## Inpainting
  * AOT is from [manga-image-translator](https://github.com/zyddnys/manga-image-translator).
  * All lama* are finetuned using [LaMa](https://github.com/advimman/lama)
  * PatchMatch is an algorithm from [PyPatchMatch](https://github.com/vacancy/PyPatchMatch), this program uses a [modified version](https://github.com/dmMaze/PyPatchMatchInpaint) by me.

## Translators
* See [How to add a new translator](doc/how_to_add_new_translator.md) for the translator module extension guide.

## FAQ & Misc
* If your computer has an Nvidia GPU or Apple silicon, the program will enable hardware acceleration.
* Accelarate performance if you have a [NVIDIA's CUDA](https://pytorch.org/docs/stable/notes/cuda.html) or [AMD's ROCm](https://pytorch.org/docs/stable/notes/hip.html) device as most modules uses [PyTorch](https://pytorch.org/get-started/locally/).
* Fonts are from your system's fonts.
* Thanks to [bropines](https://github.com/bropines) for the Russian localization.
* The initial German UI catalog for this fork was generated locally with [TranslateGemma](https://ai.google.dev/gemma/docs/translation) and validated for Qt placeholders and catalog completeness.
* Added Export to photoshop JSX script by [bropines](https://github.com/bropines). </br> To read the instructions, improve the code and just poke around to see how it works, you can go to `scripts/export to photoshop` -> `install_manual.md`.
* The project-local Python and virtual-environment bootstrap uses [uv](https://github.com/astral-sh/uv), distributed under the Apache-2.0 or MIT license.
* Additional fork attribution and license notes are collected in [CREDITS.md](CREDITS.md).
