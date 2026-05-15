# Two-Step Refinement Robustness Notes

## Current flow

`TwoStepTranslator` first calls the configured `first step translator` (`google`, `DeepL Free`, or `DeepL`) and stores those results as `first_step_draft` values. `pretranslate_textblk_lst` writes the draft to `translation_draft`; `translate_textblk_lst` writes it again before calling the LLM-backed `translate` path.

The normal refinement request sends a compact list of items:

```json
[
  {"id": 1, "source": "source text", "draft_translation": "first-step draft"}
]
```

The expected `TranslationResponse` schema is:

```json
{
  "translations": [
    {"id": 1, "translation": "final improved translation"}
  ]
}
```

The `fallback to first step` setting is now the final `draft_fallback`: it uses the Google/DeepL/first-step drafts only after `normal_llm_refinement` and `strict_llm_refinement_retry` fail to provide usable ID-matched translations. It does not run another LLM step by itself.

## Found cause

The logged failures came from local Ollama models returning schema-invalid JSON for refinement, especially `{}` or a single object such as `{"id":8,"source":"...","draft_translation":"..."}`. The old count validation treated `0 != expected` or `1 != expected` as a whole-chunk failure, so usable ID-matched LLM output was discarded and the translator fell directly back to first-step drafts.

A second issue was fallback detection based on text equality. If the LLM correctly returned the draft unchanged because it was already good, the result could be logged and marked as `draft_fallback`. Fallback tracking now records only IDs actually filled from draft during `partial_refinement_merge`.

## Prompt separation

- `normal_llm_refinement`: short schema-first prompt for improving `source` plus `draft_translation`.
- `strict_llm_refinement_retry`: one short retry prompt listing `Required IDs`; used only after empty, malformed, partial, missing-ID, extra-ID, count-mismatch, or parse-failure responses.
- `reflection`: optional review pass using `TranslationResponse`, separate from refinement retry.
- `glossary`: glossary usage is terminology guidance only.
- `glossary build`: separate extraction prompt using `GlossaryResponse`.

Glossary text can be appended to normal refinement through the review glossary section when enabled, but the strict retry avoids glossary, reflection, and extraction instructions.

## Normalization

`_normalize_translation_response_data` accepts:

- `{"translations":[...]}`
- a root list, wrapped as `translations`
- a single dict with `id` and `translation`
- a single dict with `id` and `draft_translation`

It normalizes string IDs to integers when possible, copies `draft_translation` into `translation` only when `translation` is missing, ignores `source` in final output, drops entries without usable `id` or translation text, and normalizes `{}` to `{"translations":[]}` with a warning instead of raising.

## Validation and merge

Count and ID validation happen in `TwoStepTranslator._response_covers_expected_ids` and `_log_refinement_shape`. The merge path never maps by position. `merge_refinement_with_drafts` uses this priority per ID:

1. `strict_llm_refinement_retry`
2. `normal_llm_refinement`
3. `first_step_draft`, only when final draft fallback is enabled
4. empty/unmodified placeholder according to existing fallback-disabled behavior

Extra IDs are ignored, missing IDs are logged, and partial responses are retained for valid expected IDs.

## Ollama request handling

Ollama requests use OpenAI-compatible `json_object` response mode. Request logs include purpose, provider, model, JSON mode, reasoning/think state, `num_ctx`, max tokens, expected count, expected IDs, and prompt length.

Reasoning is controlled by the existing `reasoning` setting. For Ollama, the request body passes `think: false` when reasoning is disabled and `think: true` when enabled. Refinement max tokens are clamped to 8192 for JSON stability; the recommended local-model range is 2048 to 4096. Strict retry uses the same compact expected IDs and prompt shape, with no extra reflection or glossary-build context.

## Chunking

`max refinement items per request` defaults to 8. Large pages are split into independent chunks, each with its own expected IDs, normal refinement request, and at most one strict retry. Results are reassembled in source order by expected ID.

## Tests

The fake-response tests cover normalization, empty responses, single-object responses, strict retry, partial merge, wrong and extra IDs, disabled draft fallback, chunking, prompt separation, and the case where the LLM intentionally copies a draft unchanged without triggering draft-fallback status.
