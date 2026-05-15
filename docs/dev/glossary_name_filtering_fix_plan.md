# Glossary Name Filtering Fix Plan

## Where glossary entries are generated

- `modules/translators/trans_llm_api.py` builds the automatic glossary prompt in `_build_glossary_extraction_prompt()`.
- `_update_glossary_from_batch()` sends source/draft translation pairs to the LLM with `GlossaryResponse` as the expected schema.
- `modules/translators/trans_two_step.py` calls `_update_glossary_from_batch()` after the first translation pass, using source text plus draft translations.

## Where categories are normalized

- `GlossaryEntry` and `GlossaryResponse` define the structured response model in `modules/translators/trans_llm_api.py`.
- `_normalize_glossary_response_data()` wraps loose LLM shapes into `{"entries": [...]}`, normalizes `notes` to `note`, normalizes aliases, and calls `canonicalize_glossary_category()`.
- `canonicalize_glossary_category()` already maps aliases such as `name` and `names` to `character`.
- `_save_glossary_entries()` checks enabled categories, deduplicates against existing source/target/alias terms, and appends new formatted lines.

## Why interjections and sentences are accepted now

- The prompt asks the model to omit generic words, full sentences, and ordinary dialogue, but it does not give enough negative examples for Japanese reactions, moans, SFX, punctuation-only strings, or dialog commands/questions.
- `_normalize_glossary_response_data()` only normalizes shape/category; it does not reject bad `character` or `title` candidates.
- `_save_glossary_entries()` rejects empty, disabled, and duplicate entries, but it trusts the category assigned by the model. A hallucinated `character` or `title` category can therefore persist.
- `title` is broad enough that commands/questions such as `待ってよ！` or `タクシー止めていい？` can pass if the LLM labels them as titles.

## Planned filter and prompt rules

- Harden `_build_glossary_extraction_prompt()` and glossary system prompt:
  - require JSON only and never `{}`;
  - require `{"entries":[]}` for no valid entries;
  - explicitly forbid classifying interjections, moans, SFX, punctuation, and normal dialogue as names or titles;
  - define strict `character` and `title` rules with examples.
- Add a post-LLM glossary entry validator before merge:
  - normalize `name` to `character`;
  - respect disabled categories;
  - reject unknown categories unless they clearly map to a known category;
  - reject punctuation-only, empty, interjection/SFX, sentence-like, invalid title, low-confidence no-name-feature, and duplicate candidates;
  - keep plausible Japanese names, kana names with honorifics, kanji names, and repeated-name-like forms.
- Improve logging in `_save_glossary_entries()`:
  - raw entries count;
  - normalized entries count;
  - accepted entries count;
  - rejected entries count;
  - reason-level diagnostics such as `interjection_or_sfx`, `punctuation_only`, `sentence_like`, `category_disabled`, `invalid_title`, `duplicate`, and `empty_source_or_target`.
- Preserve manual entries:
  - existing glossary lines stay dominant;
  - automatic entries are only appended when not duplicate/conflicting;
  - automatic filtering never deletes existing manual lines.

## Tests

- Add synthetic tests for positive Japanese names and negative interjections/dialogue/title cases.
- Cover `name -> character`, disabled categories, duplicate prevention, manual-entry preservation, and empty LLM response behavior.
- Tests use fake translator/logger objects and string payloads only; no real API calls, model files, cache, debug files, or manga/comic images.
