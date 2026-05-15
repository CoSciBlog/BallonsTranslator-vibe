import argparse
import json
import os.path as osp
import sys
from typing import List

APP_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from benchmarks.llm_model_matrix import BenchmarkConfig, BenchmarkInput, run_benchmark_matrix
from utils.config import pcfg


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in (value or "").replace("\n", ",").split(",") if item.strip()]


def _load_texts(args) -> List[str]:
    texts = []
    if args.texts:
        texts.extend([item.strip() for item in args.texts.split("||")])
    if args.texts_file:
        with open(args.texts_file, "r", encoding="utf-8") as fh:
            if args.texts_file.lower().endswith(".json"):
                payload = json.load(fh)
                if isinstance(payload, list):
                    texts.extend(str(item) for item in payload)
                else:
                    texts.extend(str(item) for item in payload.get("texts", []))
            else:
                texts.extend(line.rstrip("\n") for line in fh if line.strip())
    return texts


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LLM model matrix translation benchmarks.")
    parser.add_argument("--models", required=True, help="Comma-separated model IDs, e.g. translategemma:12b,qwen3.5:9b")
    parser.add_argument("--translator-types", default="llm,two_step", help="Comma-separated: llm,two_step")
    parser.add_argument("--runs-per-model", type=int, default=1)
    parser.add_argument("--warmup-runs", type=int, default=0)
    parser.add_argument("--provider", default="Ollama")
    parser.add_argument("--endpoint", default="http://localhost:11434/v1")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--num-predict", type=int, default=None)
    parser.add_argument("--num-ctx", type=int, default=None)
    parser.add_argument("--reasoning", action="store_true")
    parser.add_argument("--no-json-mode", action="store_true")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--source-lang", default=None)
    parser.add_argument("--target-lang", default=None)
    parser.add_argument("--texts", default="", help="Inline texts separated by ||")
    parser.add_argument("--texts-file", default="", help="TXT or JSON file with benchmark source texts")
    parser.add_argument("--output-dir", default=osp.join("benchmarks", "results"))
    args = parser.parse_args()

    source_texts = _load_texts(args)
    if not any(text.strip() for text in source_texts):
        parser.error("Provide at least one source text with --texts or --texts-file.")

    config = BenchmarkConfig(
        models=_split_csv(args.models),
        translator_types=_split_csv(args.translator_types),
        runs_per_model=max(1, args.runs_per_model),
        provider=args.provider,
        endpoint=args.endpoint,
        max_tokens=args.max_tokens,
        num_predict=args.num_predict,
        num_ctx=args.num_ctx,
        reasoning=bool(args.reasoning),
        json_mode=not args.no_json_mode,
        source_lang=args.source_lang or pcfg.module.translate_source,
        target_lang=args.target_lang or pcfg.module.translate_target,
        timeout_seconds=args.timeout,
        warmup_runs=max(0, args.warmup_runs),
        output_dir=args.output_dir,
        base_translator_params=pcfg.module.translator_params,
    )
    result = run_benchmark_matrix(BenchmarkInput(source_texts=source_texts), config)
    print(result.summary)
    print(f"JSON: {result.artifacts.json_path}")
    print(f"CSV: {result.artifacts.csv_path}")
    print(f"Summary: {result.artifacts.summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
