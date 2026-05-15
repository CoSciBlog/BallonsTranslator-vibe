# Review Pronoun And Name Glossary Plan

## Current Review Pipeline

- `LLM_API_Translator._request_translation()` optionally runs reflection after the initial structured translation response.
- `LLM_API_Translator._build_reflection_prompt()` builds the review prompt from the original translation prompt and the draft `TranslationResponse`.
- `TwoStepTranslator` creates first-step machine translation drafts, then sends source and `draft_translation` pairs through LLM refinement.
- Review/refinement responses are parsed as `TranslationResponse`, preserving numeric IDs and expected item counts.

## Current Glossary Pipeline

- Project glossary text and prompt are stored in each project's `imgtrans_*.json` under `glossary`.
- The translator receives project glossary data through `set_project_glossary()` and writes updated entries back through `get_project_glossary()`.
- Automatic glossary extraction uses `GlossaryResponse` and `_update_glossary_from_batch()`.
- Glossary entries are line-based: `source => target [category] # optional note`.
- Existing category settings control which automatic categories are allowed.

## Planned Changes

- Normalize `name` category values to `character`.
- Extract character/person names from source and draft translations during the first translation pass.
- Preserve existing glossary entries and skip automatic entries that conflict with existing source terms, normalized spellings, or aliases.
- Support aliases from model output and store them in glossary notes as `aliases: ...`.
- Pass compact review glossary guidance for `character`, `honorific`, `title`, `place`, and `organization`.
- Extend review prompts with pronoun, speaker/addressee, and address-form checks.
- Keep glossary metadata out of translation output.

## Affected Files

- `modules/translators/trans_llm_api.py`
- `modules/translators/trans_two_step.py`
- `tests/test_glossary_response_normalization.py`
- `tests/test_llm_prompt_separation.py`
- `tests/test_two_step_fallback.py`
- `README.md`
- `CHANGELOG.md`

## Risks

- Extra glossary extraction before review can add LLM/API cost in Two-Step translation.
- Line-based glossary storage cannot perfectly distinguish manual entries from older automatic entries, so all existing entries are treated as dominant.
- Pronoun and address-form fixes depend on available source/context/glossary information; the prompt forbids inventing unknown details.

## Tests

- Validate `name` to `character` normalization.
- Validate empty glossary responses do not crash.
- Validate alias parsing and deduplication.
- Validate existing manual entries are preserved.
- Validate disabled automatic categories are respected.
- Validate review prompts include pronoun/address rules, TranslationResponse schema, stable IDs/count requirements, and compact glossary guidance.
