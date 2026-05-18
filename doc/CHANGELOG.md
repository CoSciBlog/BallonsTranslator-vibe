# Changelogs

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

[v1.4.0-vibe.3] two-step background pretranslation
1. Added an optional `parallel first step during pipeline` mode for the `Two-Step Translator`.
2. When enabled, Google or DeepL draft translations start in the background after OCR finishes for each page while the remaining OCR/inpainting work continues.
3. The final Ollama/LLM refinement step waits until detection, OCR, and inpainting are complete, then reuses the cached first-step drafts.
4. Added an optional `unload vision models before llm` setting to free text detection, OCR, and inpainting models from RAM/VRAM before the final local LLM calls.

[v1.4.0-vibe.2] settings export and preset management
1. Added settings export/import actions in the General settings panel.
2. Added named settings presets stored under `config/presets`, with UI actions to save, apply, import, and export presets.
3. Re-synchronizes active module selectors and runtime module instances after importing settings or applying a preset.
4. Ignored local preset JSON files in Git because they may contain endpoints, prompts, model names, or API keys.

[v1.4.0-vibe.1] fork documentation and release identity refresh
1. Introduced the fork-aware application version `1.4.0-vibe.1` so this build is clearly distinguishable from upstream `1.4.0`.
2. Replaced the root `README.md` with the English README and refreshed the English documentation for the fork.
3. Documented the Pinokio launcher flow, the shared `./env` virtual environment, and the fork update path to `CoSciBlog/BallonsTranslator-vibe` on `dev`.
4. Recorded that this project is maintained as a Codex-expanded fork with launcher and documentation work layered on top of the upstream desktop app.
5. Added explicit disclosure that translated output and some documentation assets are machine-translated and should be labeled accordingly when republished.

### 2023-04-15
支持从某些源站下载/更新图片，感谢[ROKOLYT](https://github.com/ROKOLYT)

### 2023-02-27
[v1.3.34](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.34) 发布
1. 修复繁体直排bug (#96)
2. 彩云和deepl目标语言支持繁体 (#100)
3. 支持读取.webp图片 (#85)

### 2023-02-23
[v1.3.30](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.30) 发布
1. 从PyQt5换到PyQt6以支持更好的嵌字预览, [避免PyQt5与nuitka的线程兼容性问题](https://github.com/Nuitka/Nuitka/issues/251)
2. 支持改变嵌字层透明度 (#88) 注意只是预览, 不会改变渲染结果, 嵌字透明度在右侧菜单效果里改
3. log文件写进data/logs

### 2023-01-27
[v1.3.26](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.26) 发布
1. 选中文本迷你菜单支持*聚合词典专业划词翻译*[沙拉查词](https://saladict.crimx.com): [安装说明](doc/saladict_chs.md)
<img src = "./src/saladict_doc.jpg">

2. 支持替换OCR和机翻结果中的关键字, 见编辑菜单或设置面板 [#78](https://github.com/dmMaze/BallonsTranslator/issues/78)
3. 支持拖拽导入文件夹 [#77](https://github.com/dmMaze/BallonsTranslator/issues/77)
4. 编辑文本时隐藏控制小方块 [#81](https://github.com/dmMaze/BallonsTranslator/issues/81)
5. 修Bug

### 2023-01-08
[v1.3.22](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.22) 发布
1. 支持删除并恢复被抹除文字
2. 支持角度复位
3. 修Bug

### 2022-12-30
[v1.3.20](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.20)发布
1. 适应具有极端宽高比的图片比如条漫
2. 支持粘贴到多个选中的文本编辑框
3. 修bug
4. OCR/翻译/修复选中文字区域, 填字样式会继承选中的文字框自己的
   单行文本建议选用ctc_48px, 多行日文选mangocr, 目前对多行其它语言不太行, 需要重新训练检测模型  
   注意如果用**ctc_48px**要保证框在竖排模式下且尽可能贴合单行文本
<img src="./src/ocrselected.gif" div align=center>

### 2022-11-29
[v1.3.15](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.15)发布
1. 修bug
2. 优化保存逻辑
3. 画笔现在可以改成方形(实验)

### 2022-10-25
[v1.3.14](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.14)发布
1. 修bug

### 2022-09-30
v1.3.13起支持深色模式: 视图->深色模式

### 2022-09-24
[v1.3.12](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.12)发布

1. 支持全局(Ctrl+G)/当前页(Ctrl+F)查找替换
2. 原来的文本编辑器局部撤销重做并入全局文本编辑撤销重做栈, 画板撤销重做现在和文本编辑分离
3. Word文档导入导出bug修复
4. 基于 https://github.com/zhiyiYo/PyQt-Frameless-Window 重写无边框窗口

### 2022-09-13
[v1.3.8](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.8)发布

1. 画笔工具修复及优化
2. 修正界面缩放
3. 支持添加自定义字体样式预设, 支持调整文字透明度和阴影, 详见https://github.com/dmMaze/BallonsTranslator/pull/38
4. 支持导入导出word文档, 支持打开*.json项目文件, 详见https://github.com/dmMaze/BallonsTranslator/pull/40

### 2022-08-31
[v1.3.4](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.4)发布

1. 添加离线日译英模型Sugoi Translator(仅日译英, 作者[mingshiba](https://www.patreon.com/mingshiba), 已获得集成授权), 感谢[@Snowad14](https://github.com/Snowad14)提供CT2转换模型
2. 来自[bropines](https://github.com/bropines)的俄语本地化支持
3. 文本编辑支持字距调节
4. 调整竖排符号及半角字符位置规则, 详见https://github.com/dmMaze/BallonsTranslator/pull/30

### 2022-08-17
[v1.3.0](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.3.0)发布

1. 修复DeepL翻译器的bug, 感谢[@Snowad14](https://github.com/Snowad14)
2. 修复部分字体偏小+轮廓导致看不清的问题
3. 支持**全局字体格式**(一键机翻字体格式): 在控制面板->嵌字菜单里将相应项从"由程序决定"改为"使用全局设置"后启用. 注意全局设置就是未编辑任何文本块时右侧字体格式面板的那些设置.  
4. 添加**新的修复模型**: lama-mpe (默认启用)
5. 文本块支持多选和**批量调整格式** (ctrl+鼠标左键或者按下右键拉框框选)
6. 支持日译英, 英译中的**自动排版**, 基于提取出的背景气泡, 目标语言为中文时会自动断句(基于pkuseg). 勾选设置面板->常规->嵌字->自动排版后将对一键机翻生效(默认启用). 

<img src="./src/multisel_autolayout.gif" div align=center>
<p align=center>
批量格式调整, 英译中自动断句分行
</p>

### 2022-05-19
[v1.2.0](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.2.0)发布

1. 支持DeepL翻译器, 感谢[@Snowad14](https://github.com/Snowad14)
2. 增加来自manga-image-translator的新OCR模型, 支持韩语识别
3. 修bug


### 2022-04-17
[v1.1.0](https://github.com/dmMaze/BallonsTranslator/releases/tag/v1.1.0)发布

1. 用qthread存编辑图片, 避免翻页卡顿
2. 图像修复策略优化: 
   - 修复算法和**CPU模式**下的修复模型输入由整张图片改为文本块
   - 可选由程序自动评估当前块是否有必要调用开销大的修复方法, 在设置-图像修复启用/禁用, 启用后纯色背景对话泡将会由计算出的背景色直接填充  
  
    优化后图像修复阶段速度提升至原来的2x-5x不等

3. 添加矩形工具
4. 更多快捷键
5. 修bug

### 2022-04-09
v1.0.0发布
