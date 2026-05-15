import csv
import json
import os.path as osp
import sys
import tempfile
import unittest

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.append(APP_ROOT)

from benchmarks.llm_model_matrix import (
    BenchmarkConfig,
    BenchmarkInput,
    build_translator_params,
    run_benchmark_matrix,
)


def param_value(params, key):
    value = params.get(key, {})
    if isinstance(value, dict):
        return value.get("value")
    return value


class FakeTranslator:
    def __init__(self, translator_type, params, source_lang, target_lang):
        self.translator_type = translator_type
        self.params = params
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.model = param_value(params, "override model")
        self.benchmark_metrics = {
            "request_count": 1,
            "normalized_response_count": 1,
            "prompt_length": 42,
            "retry_count": 0,
        }
        if translator_type == "two_step":
            self.benchmark_metrics.update(
                {
                    "first_step_duration": 0.25,
                    "llm_refinement_duration": 0.5,
                    "fallback_to_first_step_count": 1,
                    "draft_fallback_count": 1,
                    "refined_translation_count": 2,
                    "strict_refinement_retry_count": 1,
                }
            )

    def translate(self, source_texts):
        if self.model == "fail-model":
            raise RuntimeError("planned fake failure")
        return [f"{self.model}:{self.translator_type}:{text}" for text in source_texts]


def fake_factory(translator_type, params, source_lang, target_lang):
    return FakeTranslator(translator_type, params, source_lang, target_lang)


class BenchmarkModelMatrixTest(unittest.TestCase):
    def config(self, output_dir, **kwargs):
        data = {
            "models": ["model-a", "model-b"],
            "translator_types": ["llm"],
            "runs_per_model": 2,
            "provider": "Ollama",
            "endpoint": "http://localhost:11434/v1",
            "max_tokens": 1234,
            "num_ctx": 4096,
            "reasoning": False,
            "json_mode": True,
            "output_dir": output_dir,
            "timestamp": "unit_test",
        }
        data.update(kwargs)
        return BenchmarkConfig(**data)

    def test_multiple_models_and_runs_are_executed_in_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_benchmark_matrix(
                BenchmarkInput(["one", "two"]),
                self.config(tmpdir),
                translator_factory=fake_factory,
            )

        self.assertEqual(
            [(run.model, run.run_index) for run in result.runs],
            [("model-a", 1), ("model-a", 2), ("model-b", 1), ("model-b", 2)],
        )
        self.assertTrue(all(run.success for run in result.runs))

    def test_model_failure_does_not_stop_remaining_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_benchmark_matrix(
                BenchmarkInput(["one"]),
                self.config(tmpdir, models=["fail-model", "ok-model"], runs_per_model=1),
                translator_factory=fake_factory,
            )

        self.assertEqual(len(result.runs), 2)
        self.assertFalse(result.runs[0].success)
        self.assertIn("planned fake failure", result.runs[0].error_message)
        self.assertTrue(result.runs[1].success)

    def test_json_csv_and_summary_are_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_benchmark_matrix(
                BenchmarkInput(["one", "two"]),
                self.config(tmpdir, models=["model-a"], runs_per_model=1),
                translator_factory=fake_factory,
            )
            with open(result.artifacts.json_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            with open(result.artifacts.csv_path, "r", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            with open(result.artifacts.summary_path, "r", encoding="utf-8") as fh:
                summary = fh.read()

        self.assertEqual(payload["runs"][0]["model"], "model-a")
        self.assertEqual(rows[0]["model"], "model-a")
        self.assertIn("model-a", summary)
        self.assertIn("Average duration seconds", summary)

    def test_two_step_metrics_are_recorded_from_fake_translator(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_benchmark_matrix(
                BenchmarkInput(["one", "two"]),
                self.config(
                    tmpdir,
                    models=["model-a"],
                    translator_types=["two_step"],
                    runs_per_model=1,
                ),
                translator_factory=fake_factory,
            )

        run = result.runs[0]
        self.assertEqual(run.translator_type, "two_step")
        self.assertEqual(run.first_step_duration, 0.25)
        self.assertEqual(run.llm_refinement_duration, 0.5)
        self.assertEqual(run.fallback_to_first_step_count, 1)
        self.assertEqual(run.strict_refinement_retry_count, 1)

    def test_build_translator_params_sets_model_matrix_values(self):
        config = self.config("unused", models=["model-a"], num_predict=2222, json_mode=False)

        params = build_translator_params(config, "llm", "model-a")

        self.assertEqual(param_value(params, "override model"), "model-a")
        self.assertEqual(param_value(params, "provider"), "Ollama")
        self.assertEqual(param_value(params, "max tokens"), 2222)
        self.assertEqual(param_value(params, "num ctx"), 4096)
        self.assertFalse(param_value(params, "json mode"))


if __name__ == "__main__":
    unittest.main()
