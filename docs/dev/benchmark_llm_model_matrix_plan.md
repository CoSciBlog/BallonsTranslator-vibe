# LLM Benchmark Model Matrix Plan

## Existing benchmark flow

- The current benchmark UI is `ui/translation_benchmark.py`.
- `TranslationBenchmarkWindow` is opened from the Run menu through `TitleBar.translation_benchmark_trigger` in `ui/mainwindowbars.py` and `MainWindow.show_translation_benchmark_window()` in `ui/mainwindow.py`.
- It collects source text from the current page only and runs selected translators in `TranslationBenchmarkWorker`.
- Results are shown read-only in a side-by-side table. The benchmark does not write translations back into project pages.

## Current translator and model selection

- The standard benchmark uses translator names selected in the UI list.
- Translator parameters come from `pcfg.module.translator_params`.
- `LLM_API_Translator` lives in `modules/translators/trans_llm_api.py`.
- `Two-Step Translator` lives in `modules/translators/trans_two_step.py` and extends `LLM_API_Translator`.
- LLM provider, model, override model, endpoint, reasoning, max tokens, glossary, context, retry, and reflection settings are all translator params.
- The current LLM request path always enables JSON response format for OpenAI-compatible providers that support it.
- Ollama reasoning/think is passed through `_build_reasoning_extra_body()`. `num_ctx` is logged if present in provider extra body, but there is not yet a user-facing param for it.

## Planned extension points

- Add a testable `benchmarks.llm_model_matrix` runner that accepts source texts, translator types, model list, runs per model, provider, endpoint, max tokens, context size, reasoning, JSON mode, timeout, and optional warmup runs.
- Keep benchmark execution in memory. It should instantiate translators and call `translate()` on copied source text only; project JSON and text blocks are not modified.
- Add a CLI wrapper under `scripts/benchmark_llm_model_matrix.py`.
- Add optional controls to the existing Translation Benchmark window so the current page can launch the matrix benchmark and write JSON/CSV/summary files.
- Extend LLM params minimally with `json mode` and `num ctx`, defaulting to current behavior.
- Capture metrics through a wrapper around translator request methods plus any translator-provided benchmark counters.

## Result fields

- Base fields: provider, model, translator type, run index, warmup flag, page count, text block count, source/target character counts, start/end timestamps, duration seconds, average seconds per text block, success, and error message.
- LLM fields: request count, JSON parse errors, normalized response count, empty response count, partial response count, retry count, fallback-to-first-step count, strict refinement retry count, glossary calls, reflection calls, reasoning/think, JSON mode, num ctx, max tokens/num predict, prompt length, and token counts when available.
- Two-Step fields: first-step duration, LLM refinement duration, review/reflection duration, glossary duration, refined translation count, and draft fallback count when available.

## Risks

- Real API calls must not leak API keys into logs or benchmark output.
- Timeouts can stop recording a run but cannot forcibly terminate a third-party HTTP request already running inside a translator.
- Existing translators have partial internal metrics, so some fields may be zero unless the request wrapper or translator supplies data.
- Two-Step first-step translation can call Google or DeepL; tests must use fake translators and never perform real network calls.
- Benchmark result files must stay out of Git.
