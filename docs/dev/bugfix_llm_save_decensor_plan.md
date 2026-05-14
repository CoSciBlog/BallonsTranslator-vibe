# Bugfix Plan: LLM, Project Save, and Decensor Robustness

## Scope

This note documents the current failure points from the logs and proposes small follow-up fixes. It intentionally does not change runtime behavior.

## Current Branch State

- Base branch checked before analysis: `dev`
- Bugfix branch created: `fix/llm-save-decensor-robustness`
- Recent history at branch creation included:
  - `6cdddc4 merge: settings preset layout and paddleocr startup`
  - `9f73338 fix: silence optional paddleocr startup notice`
  - `ddfd2b0 fix: adjust settings preset layout`
  - `5d06433 fix: expose censor restoration ui controls`
  - `41bcebf merge: censor restoration sidebar`

## LLM Translation Validation

`TranslationResponse` is defined in `modules/translators/trans_llm_api.py` as a Pydantic model with one required field:

- `translations: List[TranslationElement]`
- each `TranslationElement` requires `id` and `translation`

The main validation path is `LLM_API_Translator._request_translation()`. It extracts JSON from the provider response, parses it with `json.loads`, then calls:

- `TranslationResponse.model_validate(data_to_validate)`

If validation fails, the current repair path accepts only these simple alternatives:

- a dict whose keys are all numeric strings, converted to `{"translations": [{"id": int(key), "translation": value}, ...]}`
- a list, wrapped as `{"translations": simple_data}`

The current repair path does not robustly accept:

- `{}` from the provider
- a single object such as `{"id": 1, "source": "...", "draft_translation": "..."}`
- a single object such as `{"id": 1, "translation": "..."}`
- a list of objects where the provider returns `draft_translation` instead of `translation`

For `{}`, the useful behavior is not to manufacture a translation. It should be treated as a structured empty response so callers can use their normal fallback path. For Two-Step Translator, that means falling back to first-step drafts when enabled.

For a single dict, a minimal robust parser can normalize it only when it contains enough information:

- if it has `id` and `translation`, wrap it in `translations`
- if it has `id` and only `draft_translation`, return no refined translation or map to the draft only as an explicit fallback-compatible response
- if it has `source` but no translation-like field, do not treat the source as a translation

## Two-Step Translator Fallback

`modules/translators/trans_two_step.py` builds first-step draft translations with `_first_step_translate()` and stores them in `draft_list`.

The refinement path is `TwoStepTranslator._translate()`:

1. get `draft_list`
2. build the refinement prompt with `source` and `draft_translation`
3. call `_request_translation(prompt, is_reflection=True)`
4. validate count and ids
5. return refined translations
6. on exception or invalid count, log the failure
7. if `fallback to first step` is enabled, return `draft_list`

The log `LLM refinement failed: ValidationError: TranslationResponse.translations Field required` is therefore already caught by Two-Step and should fall back to `draft_list`. The weakness is that `_request_translation()` logs raw invalid JSON only at debug level after its repair attempt. A minimal fix should make the invalid-shape handling clearer and avoid noisy tracebacks while preserving the fallback.

Recommended minimal LLM fixes:

- Add a small normalization helper inside `trans_llm_api.py` for provider JSON before Pydantic validation.
- Accept `{"translations": ...}`, numeric-key dicts, lists, and single `{id, translation}` dicts.
- Treat `{}` and `{id, source, draft_translation}` as invalid/empty refinement output, not as a hard app-level failure.
- Keep Two-Step fallback behavior unchanged, but improve logging to say refinement output was empty or malformed and draft fallback was used.

## Project Save on Windows

Project saving is implemented in `utils/proj_imgtrans.py::ProjImgTrans.save()`.

Current flow:

1. build `tmp_save_tgt = self.proj_path + ".tmp"`
2. write full project JSON to the temp file
3. if backup requested, `os.replace(self.proj_path, self.proj_path + ".backup")`
4. `os.replace(tmp_save_tgt, self.proj_path)`

`os.replace()` is atomic on Windows when the destination can be replaced. It can fail with `PermissionError: [WinError 5] Access is denied` when:

- another process has the destination JSON open without delete/share-write permissions
- antivirus, indexing, sync software, backup tools, or an editor briefly locks the file
- the project directory has restrictive ACLs
- the existing destination is read-only
- concurrent saves race against each other in the app

Recommended minimal save fixes:

- Add a short retry loop around `os.replace(tmp_save_tgt, self.proj_path)` for `PermissionError` on Windows.
- Use small delays, for example 50 ms, 150 ms, 300 ms.
- Log each retry with destination and exception.
- If all retries fail, keep the `.tmp` file and raise an error that includes both source and target paths.
- Consider guarding `save()` with a per-project lock if concurrent UI/worker saves are possible.
- Do not silently delete the original project JSON after a failed replace.

## Decensor Mask Generation

The current UI button triggers the existing decensor worker path in `ui/module_manager.py`.

Relevant flow:

- `ModuleManager.runDecensorPipeline(pages_to_process=[current_page])`
- `ImgtransThread.runDecensorPipeline()`
- `ImgtransThread._decensor_pipeline()`
- `ImgtransThread._run_decensor_pages()`
- `ImgtransThread._decensor_page(imgname)`

`_decensor_page()` loads the current inpainted image or upscaled image, then calls:

- `utils.decensor.build_decensor_mask(img, mode=pcfg.decensor_mask_mode, dilate=pcfg.decensor_mask_dilate, min_area_ratio=pcfg.decensor_min_area_ratio)`

`build_decensor_mask()` combines these detectors depending on mode:

- `green_mask`
- `bar_mask`
- `mosaic_mask`

If the final mask has no positive pixels, the code logs:

- `No decensor mask found for <page>`

Then it saves an empty decensor mask and copies the input image as the decensored output.

The newer `modules/censor_restoration` detector/pipeline has optional debug output (`censor_mask.png`, overlay, boxes JSON), but the current UI decensor path does not use that module. It uses `utils.decensor` directly, so the `CensorRestorationPipeline` debug outputs are not available from the sidebar action.

## Missing Debug Data for No Mask Found

The current decensor logs do not explain why no mask was found. Useful low-risk debug data would include:

- page name
- image shape and dtype
- configured mode, dilation, and min area ratio
- per-detector candidate pixel counts before final merge
- final mask pixel count
- optional path to an overlay or empty-mask image when explicit debug output is enabled
- whether the input image came from `inpainted`, `upscaled`, or original page data

Recommended minimal decensor fixes:

- Extend `utils.decensor.build_decensor_mask()` to optionally return debug stats, without changing the default return shape.
- Log candidate counts in `_decensor_page()` when no mask is found.
- Add an explicit setting or internal debug flag before writing debug images; never write debug masks by default.
- Consider using `modules.censor_restoration.CensorMaskDetector` for simple bar detection later, but avoid mixing both detector stacks in a small bugfix unless tests cover the behavior.

## Minimal Follow-Up Implementation Plan

1. LLM robustness:
   - Add a response-normalization helper in `modules/translators/trans_llm_api.py`.
   - Add synthetic unit tests for `{}`, single `{id, translation}`, single `{id, source, draft_translation}`, numeric-key dict, and list responses.
   - Confirm Two-Step keeps returning first-step drafts when refinement is empty or malformed.

2. Save robustness:
   - Add retry-on-`PermissionError` around `os.replace` in `utils/proj_imgtrans.py::save()`.
   - Keep temp file on final failure.
   - Add a small unit test around a mocked `os.replace` that fails once then succeeds.

3. Decensor diagnostics:
   - Add optional stats from `utils.decensor` without writing files.
   - Log stats from `_decensor_page()` when no mask is found.
   - Add synthetic tests with generated arrays only.

## Constraints

- No model files.
- No cache files.
- No debug images committed.
- No real manga, comic, NSFW, or copyrighted test images.
- Keep implementation changes small and isolated in the follow-up bugfix step.
