#!/usr/bin/env python3
"""Validate a Tokyo/CSAT experiment package and export local integration data.

This is NOT an uploader or the live website's confirmed import format.
Only integer/choice-answer API runs and the packaged Motif manual format are
supported. No evaluation APIs, dependencies, or network access are required.
"""

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def grade(row):
    if row.get("error") or row.get("timeout"):
        return False
    if "correct" in row:
        if type(row["correct"]) is not bool:
            raise ValueError("Manual correct flag must be boolean")
        return row["correct"]
    gold = "" if row.get("gold_answer") is None else str(row["gold_answer"]).strip()
    if not gold:
        raise ValueError("Missing gold answer")
    pred = "" if row.get("final_answer") is None else str(row["final_answer"]).strip()
    if gold in ("①", "②", "③", "④", "⑤"):
        # Preserve the package's strict choice-symbol grading (3 != ③).
        return pred == gold
    try:
        gold_number = Decimal(gold)
    except InvalidOperation as exc:
        raise ValueError(f"Unsupported nonnumeric gold answer: {gold!r}") from exc
    if not gold_number.is_finite() or gold_number != gold_number.to_integral_value():
        raise ValueError(f"Unsupported noninteger gold answer: {gold!r}")
    try:
        return Decimal(pred) == gold_number
    except InvalidOperation:
        return False


def summarize(rows, problem_count, start_idx=0):
    runs = {}
    for row in rows:
        key = (row["id"], row["run_idx"])
        if type(key[0]) is not int or type(key[1]) is not int:
            raise ValueError(f"Noninteger problem/run ID: {key}")
        if key in runs:
            raise ValueError(f"Duplicate problem/run: {key}")
        runs[key] = row
    expected = {(pid, run) for pid in range(start_idx, start_idx + problem_count)
                for run in range(3)}
    if not expected or set(runs) != expected:
        raise ValueError(f"Incomplete or unexpected runs: missing={sorted(expected - runs.keys())}, "
                         f"unexpected={sorted(runs.keys() - expected)}")
    flags = {key: grade(row) for key, row in runs.items()}
    problem_stats = {
        str(pid): {"correct": sum(flags[(pid, i)] for i in range(3)), "total": 3}
        for pid in range(start_idx, start_idx + problem_count)
    }
    return {
        "problem_count": problem_count,
        "run_count": len(runs),
        "error_count": sum(bool(r.get("error") or r.get("timeout")) for r in rows),
        "correct_runs": sum(flags.values()),
        "accuracy_at_1": sum(value for (_, i), value in flags.items() if i == 0) / problem_count,
        "run_accuracy": sum(flags.values()) / len(runs),
        "pass_at_3": sum(p["correct"] > 0 for p in problem_stats.values()) / problem_count,
        "problem_stats": problem_stats,
    }


def prepare(package):
    models = []
    expected_counts = {"tokyo_math_hf_private": (30, 7), "csat_2026_math_en": (46, 3)}
    model_keys = set()
    for manifest_path in sorted((package / "results").rglob("run_manifest.json")):
        manifest = read_json(manifest_path)
        comp = manifest["competition"]
        dataset = comp["name"]
        if dataset not in expected_counts or comp["n_rows_loaded"] != expected_counts[dataset][0]:
            raise ValueError(f"Unsupported benchmark in {manifest_path}")
        if manifest["n_repeats"] != 3:
            raise ValueError(f"Expected exactly three repeats: {manifest_path}")
        model_id = manifest["model"]["model"]
        if (dataset, model_id) in model_keys:
            raise ValueError(f"Duplicate model: {dataset}/{model_id}")
        model_keys.add((dataset, model_id))
        rows = [read_json(p) for p in sorted(manifest_path.parent.glob("*_run_*.json"))]
        models.append({
            "dataset": dataset, "model": model_id, "evaluation_mode": "api",
            "source": str(manifest_path.parent.relative_to(package)),
            **summarize(rows, comp["n_rows_loaded"], comp["start_idx"]),
        })
    for dataset, (_, count) in expected_counts.items():
        if sum(m["dataset"] == dataset for m in models) != count:
            raise ValueError(f"Expected {count} API models for {dataset}")
    manual_path = (package / "results/csat_2026_math/motif3_web_chat/"
                   "motif_manual_web_eval/motif3_csat_web_results.jsonl")
    rows = [json.loads(line) for line in manual_path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    if any("correct" not in row for row in rows):
        raise ValueError("Missing manual grading flag")
    models.append({
        "dataset": "csat_2026_math_en", "model": "Motif 3 web chat",
        "evaluation_mode": "manual_web_chat", "response_level": "중간",
        "source": str(manual_path.relative_to(package)), **summarize(rows, 46),
    })
    return {
        "schema_version": 1,
        "status": "local_preparation_only_not_confirmed_website_schema",
        "metric_definitions": {
            "accuracy_at_1": "Correct run_idx=0 / all problems, including errors as incorrect",
            "run_accuracy": "Correct runs / all three attempts per problem, including errors",
            "pass_at_3": "Problems with at least one correct answer across exactly three runs / all problems",
            "units": "Fractions in [0, 1], not percentages",
        },
        "notes": [
            "Tokyo private dataset: do not publish questions, answers, or raw traces without approval.",
            "English CSAT results must not be merged into KOR_CSAT_26_KOR without dataset verification.",
            "Motif uses existing manual correct flags; API runs use strict choice/integer grading.",
            "Existing summaries can exclude errors; this export includes all scheduled attempts.",
            "No tokens, timings, raw text, credentials, or absolute source paths are exported.",
        ],
        "model_count": len(models), "run_count": sum(m["run_count"] for m in models),
        "models": models,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    output = args.output.resolve()
    if output.is_relative_to(package):
        parser.error("Output must be outside the original experiment package")
    # Validate everything before opening the output file.
    result = prepare(package)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Validated {result['model_count']} models / {result['run_count']} runs: {output}")


if __name__ == "__main__":
    main()
