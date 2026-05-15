import copy
import csv
import json
import os
import os.path as osp
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import ValidationError

from modules.translators.trans_llm_api import LLM_API_Translator
from modules.translators.trans_two_step import TwoStepTranslator
from utils.logger import logger as LOGGER


SENSITIVE_PARAM_KEYS = {
    "apikey",
    "api_key",
    "multiple_keys",
    "deepl api key",
    "deepl_api_key",
    "proxy",
}


@dataclass
class BenchmarkInput:
    source_texts: List[str]
    page_count: int = 1
    page_keys: List[str] = field(default_factory=list)

    @property
    def text_block_count(self) -> int:
        return len([text for text in self.source_texts if str(text or "").strip()])

    @property
    def source_character_count(self) -> int:
        return sum(len(text or "") for text in self.source_texts)


@dataclass
class BenchmarkConfig:
    models: List[str]
    translator_types: List[str] = field(default_factory=lambda: ["llm", "two_step"])
    runs_per_model: int = 1
    provider: str = "Ollama"
    endpoint: str = "http://localhost:11434/v1"
    max_tokens: int = 4096
    num_ctx: Optional[int] = None
    num_predict: Optional[int] = None
    reasoning: bool = False
    json_mode: bool = True
    source_lang: str = "Auto"
    target_lang: str = "English"
    timeout_seconds: Optional[float] = None
    warmup_runs: int = 0
    output_dir: str = osp.join("benchmarks", "results")
    timestamp: Optional[str] = None
    base_translator_params: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class BenchmarkRunResult:
    provider: str
    model: str
    translator_type: str
    run_index: int
    warmup: bool
    page_count: int
    text_block_count: int
    source_character_count: int
    target_character_count: int
    start_time: str
    end_time: str
    duration_seconds: float
    average_seconds_per_text_block: float
    success: bool
    error_message: str = ""
    request_count: int = 0
    json_parse_errors: int = 0
    normalized_response_count: int = 0
    empty_response_count: int = 0
    partial_response_count: int = 0
    retry_count: int = 0
    fallback_to_first_step_count: int = 0
    strict_refinement_retry_count: int = 0
    glossary_build_calls: int = 0
    reflection_calls: int = 0
    reasoning: bool = False
    think: Optional[bool] = None
    json_mode: bool = True
    num_ctx: Optional[int] = None
    num_predict: Optional[int] = None
    max_tokens: Optional[int] = None
    prompt_length: int = 0
    prompt_length_max: int = 0
    generated_token_count: int = 0
    prompt_token_count: int = 0
    total_token_count: int = 0
    first_step_duration: float = 0.0
    llm_refinement_duration: float = 0.0
    review_reflection_duration: float = 0.0
    glossary_duration: float = 0.0
    refined_translation_count: int = 0
    draft_fallback_count: int = 0


@dataclass
class BenchmarkArtifacts:
    json_path: str
    csv_path: str
    summary_path: str


@dataclass
class BenchmarkResult:
    config: BenchmarkConfig
    runs: List[BenchmarkRunResult]
    artifacts: BenchmarkArtifacts
    summary: str


TranslatorFactory = Callable[[str, Dict[str, Dict[str, Any]], str, str], Any]


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _set_param(params: Dict[str, Dict[str, Any]], key: str, value: Any) -> None:
    current = params.get(key)
    if isinstance(current, dict):
        current["value"] = value
    else:
        params[key] = {"value": value}


def _translator_param_key(translator_type: str) -> str:
    if translator_type == "llm":
        return "LLM_API_Translator"
    if translator_type == "two_step":
        return "Two-Step Translator"
    raise ValueError(f"Unsupported translator type: {translator_type}")


def build_translator_params(
    config: BenchmarkConfig,
    translator_type: str,
    model: str,
) -> Dict[str, Dict[str, Any]]:
    param_key = _translator_param_key(translator_type)
    params = copy.deepcopy(config.base_translator_params.get(param_key, {}))
    defaults = (
        TwoStepTranslator.params if translator_type == "two_step" else LLM_API_Translator.params
    )
    if not params:
        params = copy.deepcopy(defaults)

    _set_param(params, "provider", config.provider)
    _set_param(params, "endpoint", config.endpoint)
    _set_param(params, "override model", model)
    _set_param(params, "max tokens", int(config.num_predict or config.max_tokens))
    _set_param(params, "reasoning", bool(config.reasoning))
    _set_param(params, "json mode", bool(config.json_mode))
    if config.num_ctx is not None:
        _set_param(params, "num ctx", int(config.num_ctx))
    return params


def default_translator_factory(
    translator_type: str,
    params: Dict[str, Dict[str, Any]],
    source_lang: str,
    target_lang: str,
) -> Any:
    translator_cls = TwoStepTranslator if translator_type == "two_step" else LLM_API_Translator
    return translator_cls(
        source_lang,
        target_lang,
        raise_unsupported_lang=False,
        **params,
    )


def _redact_value(key: str, value: Any) -> Any:
    normalized = key.strip().lower()
    if normalized in SENSITIVE_PARAM_KEYS or "key" in normalized and "monkey" not in normalized:
        if isinstance(value, str) and value:
            return "[REDACTED]"
        if value:
            return "[REDACTED]"
    return value


def redact_params(params: Dict[str, Any]) -> Dict[str, Any]:
    redacted = {}
    for key, value in params.items():
        if isinstance(value, dict):
            item = dict(value)
            if "value" in item:
                item["value"] = _redact_value(key, item["value"])
            redacted[key] = item
        else:
            redacted[key] = _redact_value(key, value)
    return redacted


class TranslatorMetricProbe:
    def __init__(self, translator: Any) -> None:
        self.translator = translator
        self.metrics = {
            "request_count": 0,
            "json_parse_errors": 0,
            "normalized_response_count": 0,
            "empty_response_count": 0,
            "partial_response_count": 0,
            "retry_count": 0,
            "fallback_to_first_step_count": 0,
            "strict_refinement_retry_count": 0,
            "glossary_build_calls": 0,
            "reflection_calls": 0,
            "prompt_length": 0,
            "prompt_length_max": 0,
            "first_step_duration": 0.0,
            "llm_refinement_duration": 0.0,
            "review_reflection_duration": 0.0,
            "glossary_duration": 0.0,
        }
        self._originals: Dict[str, Callable] = {}

    def install(self) -> None:
        self._wrap_request("_request_translation")
        self._wrap_request("_request_model_object")
        self._wrap_timed("_first_step_translate", "first_step_duration")
        self._wrap_timed("_request_refinement_chunk", "llm_refinement_duration")
        self._wrap_timed("_refine_translations_with_glossary", "glossary_duration")

    def _wrap_request(self, name: str) -> None:
        original = getattr(self.translator, name, None)
        if original is None:
            return
        self._originals[name] = original

        def wrapped(prompt, *args, **kwargs):
            purpose = kwargs.get("purpose") or ("translation" if name == "_request_translation" else "model_object")
            prompt_length = len(prompt or "")
            self.metrics["request_count"] += 1
            self.metrics["prompt_length"] += prompt_length
            self.metrics["prompt_length_max"] = max(self.metrics["prompt_length_max"], prompt_length)
            if purpose == "strict_refinement_retry":
                self.metrics["strict_refinement_retry_count"] += 1
                self.metrics["retry_count"] += 1
            elif purpose == "reflection":
                self.metrics["reflection_calls"] += 1
            elif purpose == "glossary":
                self.metrics["glossary_build_calls"] += 1
            started = time.perf_counter()
            try:
                result = original(prompt, *args, **kwargs)
                if result is None:
                    self.metrics["empty_response_count"] += 1
                else:
                    self.metrics["normalized_response_count"] += 1
                return result
            except (json.JSONDecodeError, ValidationError):
                self.metrics["json_parse_errors"] += 1
                raise
            finally:
                if purpose == "reflection":
                    self.metrics["review_reflection_duration"] += time.perf_counter() - started

        setattr(self.translator, name, wrapped)

    def _wrap_timed(self, name: str, metric_key: str) -> None:
        original = getattr(self.translator, name, None)
        if original is None:
            return
        self._originals[name] = original

        def wrapped(*args, **kwargs):
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.metrics[metric_key] += time.perf_counter() - started

        setattr(self.translator, name, wrapped)

    def collect(self) -> Dict[str, Any]:
        collected = dict(self.metrics)
        provided = getattr(self.translator, "benchmark_metrics", None)
        if isinstance(provided, dict):
            for key, value in provided.items():
                if isinstance(value, (int, float)):
                    collected[key] = collected.get(key, 0) + value
                else:
                    collected[key] = value

        fallback_ids = getattr(self.translator, "_last_draft_fallback_ids", [])
        if fallback_ids:
            collected["fallback_to_first_step_count"] += len(fallback_ids)
            collected["draft_fallback_count"] = collected.get("draft_fallback_count", 0) + len(fallback_ids)
        if getattr(self.translator, "last_refinement_used_draft_fallback", False) and not fallback_ids:
            collected["fallback_to_first_step_count"] += 1
            collected["draft_fallback_count"] = collected.get("draft_fallback_count", 0) + 1

        token_count = getattr(self.translator, "token_count", 0) or 0
        token_count_last = getattr(self.translator, "token_count_last", 0) or 0
        collected.setdefault("total_token_count", token_count)
        collected.setdefault("generated_token_count", 0)
        collected.setdefault("prompt_token_count", 0)
        if token_count and not collected.get("generated_token_count"):
            collected["generated_token_count"] = token_count_last
        return collected


def _run_translate_with_timeout(translator: Any, source_texts: List[str], timeout_seconds: Optional[float]) -> List[str]:
    if timeout_seconds is None or timeout_seconds <= 0:
        return translator.translate(source_texts)

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(translator.translate, source_texts)
    try:
        return future.result(timeout=timeout_seconds)
    except TimeoutError:
        future.cancel()
        raise TimeoutError(f"Benchmark run timed out after {timeout_seconds} seconds")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def run_single_benchmark(
    benchmark_input: BenchmarkInput,
    config: BenchmarkConfig,
    translator_type: str,
    model: str,
    run_index: int,
    warmup: bool,
    translator_factory: TranslatorFactory,
) -> BenchmarkRunResult:
    params = build_translator_params(config, translator_type, model)
    started_iso = _utc_now()
    started = time.perf_counter()
    outputs: List[str] = []
    error_message = ""
    success = False
    probe_metrics: Dict[str, Any] = {}

    LOGGER.info(
        "Benchmark model matrix: translator=%s model=%s run=%s/%s warmup=%s",
        translator_type,
        model,
        run_index,
        config.runs_per_model,
        warmup,
    )
    try:
        translator = translator_factory(
            translator_type,
            params,
            config.source_lang,
            config.target_lang,
        )
        probe = TranslatorMetricProbe(translator)
        probe.install()
        non_empty_texts = [text for text in benchmark_input.source_texts if str(text or "").strip()]
        outputs = _run_translate_with_timeout(translator, non_empty_texts, config.timeout_seconds)
        if isinstance(outputs, str):
            outputs = [outputs]
        outputs = list(outputs or [])
        success = True
        if len(outputs) != len(non_empty_texts):
            probe.metrics["partial_response_count"] += 1
        if any(not str(text or "").strip() for text in outputs):
            probe.metrics["empty_response_count"] += 1
        if translator_type == "two_step":
            probe.metrics["refined_translation_count"] += len([text for text in outputs if str(text or "").strip()])
        probe_metrics = probe.collect()
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        LOGGER.error("Benchmark run failed for %s/%s: %s", translator_type, model, error_message)
        LOGGER.debug(traceback.format_exc())

    duration = time.perf_counter() - started
    ended_iso = _utc_now()
    avg = duration / max(1, benchmark_input.text_block_count)
    target_chars = sum(len(text or "") for text in outputs)
    result = BenchmarkRunResult(
        provider=config.provider,
        model=model,
        translator_type=translator_type,
        run_index=run_index,
        warmup=warmup,
        page_count=benchmark_input.page_count,
        text_block_count=benchmark_input.text_block_count,
        source_character_count=benchmark_input.source_character_count,
        target_character_count=target_chars,
        start_time=started_iso,
        end_time=ended_iso,
        duration_seconds=round(duration, 6),
        average_seconds_per_text_block=round(avg, 6),
        success=success,
        error_message=error_message,
        reasoning=config.reasoning,
        think=config.reasoning if config.provider == "Ollama" else None,
        json_mode=config.json_mode,
        num_ctx=config.num_ctx,
        num_predict=config.num_predict,
        max_tokens=config.max_tokens,
    )
    for key, value in probe_metrics.items():
        if hasattr(result, key):
            setattr(result, key, value)
    LOGGER.info(
        "Benchmark model matrix completed: translator=%s model=%s run=%s duration=%.3fs success=%s",
        translator_type,
        model,
        run_index,
        duration,
        success,
    )
    return result


def iter_benchmark_jobs(config: BenchmarkConfig) -> Iterable[Tuple[str, str, int, bool]]:
    for translator_type in config.translator_types:
        for model in config.models:
            for warmup_index in range(1, max(0, config.warmup_runs) + 1):
                yield translator_type, model, warmup_index, True
            for run_index in range(1, max(1, config.runs_per_model) + 1):
                yield translator_type, model, run_index, False


def summarize_runs(runs: Sequence[BenchmarkRunResult]) -> str:
    measured = [run for run in runs if not run.warmup]
    lines = ["# LLM Model Matrix Benchmark Summary", ""]
    if not measured:
        lines.append("No measured runs were recorded.")
        return "\n".join(lines)

    groups: Dict[Tuple[str, str], List[BenchmarkRunResult]] = {}
    for run in measured:
        groups.setdefault((run.translator_type, run.model), []).append(run)

    fastest_key = None
    fastest_avg = None
    for key, group in groups.items():
        successes = [run for run in group if run.success]
        avg_duration = (
            sum(run.duration_seconds for run in successes) / len(successes)
            if successes
            else 0.0
        )
        avg_fallback = (
            sum(run.fallback_to_first_step_count for run in group) / max(1, len(group))
        )
        errors = [run for run in group if not run.success]
        lines.append(f"## {key[0]} / {key[1]}")
        lines.append(f"- Runs: {len(group)}")
        lines.append(f"- Successful runs: {len(successes)}")
        lines.append(f"- Average duration seconds: {avg_duration:.3f}")
        lines.append(f"- Average fallback count: {avg_fallback:.3f}")
        lines.append(f"- Errors: {len(errors)}")
        if errors:
            first_error = errors[0].error_message[:240]
            lines.append(f"- First error: {first_error}")
        lines.append("")
        if successes and (fastest_avg is None or avg_duration < fastest_avg):
            fastest_key = key
            fastest_avg = avg_duration

    if fastest_key is not None:
        lines.append(
            f"Fastest successful average: {fastest_key[0]} / {fastest_key[1]} at {fastest_avg:.3f}s."
        )
    else:
        lines.append("No successful runs; no recommendation is available.")
    return "\n".join(lines)


def _csv_fieldnames() -> List[str]:
    return list(asdict(BenchmarkRunResult(
        provider="",
        model="",
        translator_type="",
        run_index=0,
        warmup=False,
        page_count=0,
        text_block_count=0,
        source_character_count=0,
        target_character_count=0,
        start_time="",
        end_time="",
        duration_seconds=0.0,
        average_seconds_per_text_block=0.0,
        success=False,
    )).keys())


def write_benchmark_outputs(config: BenchmarkConfig, runs: List[BenchmarkRunResult]) -> BenchmarkArtifacts:
    timestamp = config.timestamp or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_dir = config.output_dir
    os.makedirs(output_dir, exist_ok=True)
    json_path = osp.join(output_dir, f"benchmark_{timestamp}.json")
    csv_path = osp.join(output_dir, f"benchmark_{timestamp}.csv")
    summary_path = osp.join(output_dir, f"benchmark_{timestamp}_summary.md")

    sanitized_config = asdict(config)
    sanitized_config["base_translator_params"] = {
        key: redact_params(value)
        for key, value in config.base_translator_params.items()
    }
    payload = {
        "config": sanitized_config,
        "runs": [asdict(run) for run in runs],
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_csv_fieldnames())
        writer.writeheader()
        for run in runs:
            writer.writerow(asdict(run))

    summary = summarize_runs(runs)
    with open(summary_path, "w", encoding="utf-8") as fh:
        fh.write(summary)

    return BenchmarkArtifacts(json_path=json_path, csv_path=csv_path, summary_path=summary_path)


def run_benchmark_matrix(
    benchmark_input: BenchmarkInput,
    config: BenchmarkConfig,
    translator_factory: TranslatorFactory = default_translator_factory,
) -> BenchmarkResult:
    if not config.models:
        raise ValueError("At least one model must be provided.")
    if not benchmark_input.text_block_count:
        raise ValueError("At least one non-empty source text is required.")

    runs = []
    for translator_type, model, run_index, warmup in iter_benchmark_jobs(config):
        run = run_single_benchmark(
            benchmark_input,
            config,
            translator_type,
            model,
            run_index,
            warmup,
            translator_factory,
        )
        runs.append(run)

    artifacts = write_benchmark_outputs(config, runs)
    with open(artifacts.summary_path, "r", encoding="utf-8") as fh:
        summary = fh.read()
    return BenchmarkResult(config=config, runs=runs, artifacts=artifacts, summary=summary)

