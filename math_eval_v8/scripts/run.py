from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import yaml
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from math_eval_v8.dataset import load_benchmark_rows
from math_eval_v8.oracle_judge import judge_oracle_alignment
from math_eval_v8.scoring import summarize_jsonl
from math_eval_v8.solvers.lean_solver import LeanSolver
from math_eval_v8.verifiers.lean_verifier import verify_lean_code


def load_yaml(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def resolve_env(value):
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        resolved = os.environ.get(env_name)
        if not resolved:
            raise RuntimeError(f"missing environment variable: {env_name}")
        return resolved
    return value


def preflight_model_server(model_config: dict) -> dict:
    base_url = str(model_config.get("base_url") or "").rstrip("/")
    if not base_url:
        return {"ok": False, "error": "missing base_url", "models": []}
    models_url = base_url.rsplit("/v1", 1)[0] + "/v1/models"
    try:
        with urlopen(models_url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [item.get("id") for item in payload.get("data", []) if item.get("id")]
        return {
            "ok": model_config.get("model") in models,
            "base_url": base_url,
            "models_url": models_url,
            "requested_model": model_config.get("model"),
            "models": models,
            "error": None if model_config.get("model") in models else "requested model not listed by server",
        }
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "base_url": base_url,
            "models_url": models_url,
            "requested_model": model_config.get("model"),
            "models": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def preflight_lean(bench_config: dict) -> dict:
    lean_project_path = bench_config.get("lean_project_path")
    default_imports = bench_config.get("default_imports")
    imports = "\n".join(["import Mathlib"] if default_imports is None else default_imports)
    code = f"{imports}\n\ntheorem math_eval_v8_preflight : True := by\n  trivial\n"
    with tempfile.NamedTemporaryFile("w", suffix=".lean", encoding="utf-8", delete=False) as handle:
        handle.write(code)
        temp_path = handle.name
    try:
        if lean_project_path:
            cmd = ["lake", "env", "lean", temp_path]
            cwd = str(Path(lean_project_path).expanduser().resolve())
        else:
            cmd = ["lean", temp_path]
            cwd = None
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "lean_project_path": lean_project_path,
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        }
    except Exception as exc:
        return {
            "ok": False,
            "lean_project_path": lean_project_path,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Math Eval V8 Lean benchmark")
    parser.add_argument("--bench", required=True, help="Benchmark YAML path")
    parser.add_argument("--model", required=True, help="Model YAML path")
    parser.add_argument("--output", default="outputs", help="Output root")
    parser.add_argument("--n-repeats", type=int, default=1)
    parser.add_argument("--max-problems", type=int, default=None)
    parser.add_argument("--model-id-override", default=None)
    parser.add_argument("--lean-timeout", type=float, default=None)
    parser.add_argument("--repair-turns", type=int, default=0)
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--oracle-judge", action="store_true", help="Run LLM-as-a-Judge semantic oracle alignment")
    parser.add_argument("--judge-model", default=None, help="Optional judge model YAML path; defaults to the solver model")
    parser.add_argument("--lean-project-path", default=None, help="Override benchmark Lean/Lake project path")
    args = parser.parse_args()

    bench_config = load_yaml(args.bench)
    bench_config["_config_dir"] = str(Path(args.bench).resolve().parent)
    if args.lean_project_path is not None:
        bench_config["lean_project_path"] = args.lean_project_path
    model_config = load_yaml(args.model)
    if "api_key" in model_config:
        model_config["api_key"] = resolve_env(model_config["api_key"])
    if args.model_id_override:
        model_config["model"] = args.model_id_override
    judge_config = load_yaml(args.judge_model) if args.judge_model else dict(model_config)
    if "api_key" in judge_config:
        judge_config["api_key"] = resolve_env(judge_config["api_key"])
    preflight = {}
    if not args.skip_preflight:
        preflight = {
            "model_server": preflight_model_server(model_config),
            "lean": preflight_lean(bench_config),
        }

    rows = load_benchmark_rows(bench_config)
    if args.max_problems is not None:
        rows = rows[: args.max_problems]

    solver = LeanSolver(model_config, bench_config)
    bench_name = bench_config.get("name") or Path(args.bench).stem
    model_name = str(model_config["model"]).replace("/", "__")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) / bench_name / model_name / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    attempts_path = output_dir / "attempts.jsonl"

    manifest = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark": bench_config,
        "model": {k: v for k, v in model_config.items() if k != "api_key"},
        "n_repeats": args.n_repeats,
        "repair_turns": args.repair_turns,
        "preflight": preflight,
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    lean_timeout = args.lean_timeout or float(bench_config.get("lean_timeout_s", 60.0))
    default_imports = bench_config.get("default_imports")
    lean_project_path = bench_config.get("lean_project_path")

    with attempts_path.open("w", encoding="utf-8") as handle:
        for row in tqdm(rows, total=len(rows)):
            for run_idx in range(args.n_repeats):
                repair = None
                result = None
                verifier = None
                error = None
                turn = 0
                try:
                    for turn in range(max(1, args.repair_turns + 1)):
                        result = solver.solve(row, repair=repair)
                        use_row_header = bench_config.get("use_row_header", True)
                        row_imports = row.header.splitlines() if use_row_header and row.header else default_imports
                        verifier = verify_lean_code(
                            result["candidate_code"],
                            lean_project_path=lean_project_path,
                            default_imports=row_imports,
                            timeout_s=lean_timeout,
                            lean_num_threads=bench_config.get("lean_num_threads"),
                        )
                        if verifier.complete:
                            break
                        repair = verifier.summary()
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                record = {
                    "problem_id": row.problem_id,
                    "model": model_config["model"],
                    "run_idx": run_idx,
                    "turn_idx": turn,
                    "row": row.to_json(),
                    **(result or {}),
                    "verifier": verifier.to_json() if verifier else None,
                    "error": error,
                }
                if args.oracle_judge and error is None:
                    try:
                        record["oracle_alignment"] = judge_oracle_alignment(row, record, judge_config)
                    except Exception as exc:
                        record["oracle_alignment"] = {
                            "oracle_aligned_pass": False,
                            "verdict": "not_judgeable",
                            "statement_alignment_score": 0,
                            "vacuity_free": False,
                            "major_issues": [f"judge failed: {type(exc).__name__}: {exc}"],
                            "rationale": "The LLM-as-a-Judge call failed.",
                            "confidence": 0.0,
                            "judge_model": judge_config.get("model"),
                        }
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                (output_dir / f"{row.problem_id}_run_{run_idx}.json").write_text(
                    json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )

    summary = summarize_jsonl(attempts_path, output_dir / "summary.json", k=args.n_repeats)
    print(json.dumps(summary["models"], ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Results saved to {output_dir}")


if __name__ == "__main__":
    main()
