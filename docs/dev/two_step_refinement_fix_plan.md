# Two-Step Refinement Robustness Notes

## Current behavior

`TwoStepTranslator` creates first-step drafts with Google, DeepL Free, or DeepL before LLM refinement. The final `fallback to first step` path now means: use those first-step draft translations only if normal LLM refinement and the strict retry fail.

## Prompt separation

- Normal refinement prompt: edits `[{id, source, draft_translation}]` into `{"translations":[{"id":1,"translation":"..."}]}`.
- Strict retry prompt: used only after bad refinement output and lists the required IDs.
- Reflection prompt: separate optional review pass and uses `TranslationResponse`.
- Glossary usage prompt: terminology guidance only.
- Glossary build prompt: glossary extraction only and uses `GlossaryResponse`.

## Validation and merge

The response normalizer accepts a proper response object, a root list, a single translation dict, or a single dict with `draft_translation`. IDs are normalized to integers when possible. Entries without usable IDs or translations are dropped. `{}` normalizes to `{"translations":[]}` and logs a warning.

Refinement results are merged by numeric ID only. Retry output has priority over normal output, normal output has priority over draft text, and extra IDs are ignored with a warning. Missing IDs are logged and can fall back to drafts when `fallback to first step` is enabled.

## Ollama stability

Refinement requests log purpose, provider, model, JSON mode, reasoning/think, token limit, expected count, expected IDs, and prompt length. Ollama refinement requests clamp very high token limits to 8192 and set `think` from the `reasoning` setting where the API supports it.
