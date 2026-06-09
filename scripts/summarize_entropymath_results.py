#!/usr/bin/env python3
"""Summarize EntropyMath frozen-sample model outputs.

This script regrades raw run JSON files instead of trusting the runner's
`solved` flag, which only indicates final-answer extraction. It reports overall
accuracy, pass@k, bootstrap confidence intervals, stratified metrics, and basic
tool-solver telemetry.
"""

from __future__ import annotations

import argparse
import glob
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    from sympy import N, simplify
    from sympy.parsing.latex import parse_latex
    from sympy.parsing.sympy_parser import parse_expr
except Exception:  # pragma: no cover - handled by string/float fallback
    N = simplify = parse_latex = parse_expr = None


def extract_boxed(text: Any) -> str:
    if text is None:
        return ""
    text = str(text)
    if "\\boxed{" not in text:
        return text
    start = text.find("\\boxed{") + len("\\boxed{")
    balance = 1
    end = start
    while end < len(text) and balance > 0:
        if text[end] == "{":
            balance += 1
        elif text[end] == "}":
            balance -= 1
        end += 1
    if balance == 0:
        return text[start : end - 1]
    return text


def normalize_text(text: Any) -> str:
    text = extract_boxed(text)
    return text.replace("\\", "").replace(" ", "").strip()


def convert_frac(text: str) -> str:
    while "\\frac{" in text:
        start = text.find("\\frac{")
        balance = 1
        i = start + len("\\frac{")
        while i < len(text) and balance > 0:
            if text[i] == "{":
                balance += 1
            elif text[i] == "}":
                balance -= 1
            i += 1
        if balance != 0:
            break
        arg1 = text[start + len("\\frac{") : i - 1]
        if i >= len(text) or text[i] != "{":
            break
        balance = 1
        j = i + 1
        while j < len(text) and balance > 0:
            if text[j] == "{":
                balance += 1
            elif text[j] == "}":
                balance -= 1
            j += 1
        if balance != 0:
            break
        arg2 = text[i + 1 : j - 1]
        text = text[:start] + f"({arg1})/({arg2})" + text[j:]
    return text


def clean_for_sympy(value: Any) -> str:
    s = extract_boxed(value).strip()
    replacements = {
        "\\$": "",
        "$": "",
        "\\%": "/100",
        "%": "/100",
        "\\dfrac": "\\frac",
        "\\tfrac": "\\frac",
        "\\degree": "*pi/180",
        "^{\\circ}": "*pi/180",
        "^\\circ": "*pi/180",
        "\\,": "",
        "\\;": "",
        "\\:": "",
        "\\ ": "",
        "\\left": "",
        "\\right": "",
        "\\pi": "pi",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    s = convert_frac(s)
    while "^{" in s:
        start = s.find("^{")
        balance = 1
        i = start + 2
        while i < len(s) and balance > 0:
            if s[i] == "{":
                balance += 1
            elif s[i] == "}":
                balance -= 1
            i += 1
        if balance != 0:
            break
        content = s[start + 2 : i - 1]
        s = s[:start] + f"**({content})" + s[i:]
    return s


def is_equiv(pred: Any, gold: Any) -> bool:
    if normalize_text(pred) == normalize_text(gold):
        return True

    clean_pred = clean_for_sympy(pred)
    clean_gold = clean_for_sympy(gold)
    if not clean_pred or not clean_gold:
        return False

    if parse_latex is not None and parse_expr is not None:
        try:
            try:
                expr_pred = parse_latex(clean_pred)
                expr_gold = parse_latex(clean_gold)
            except Exception:
                local_dict = {"frac": lambda x, y: x / y}
                expr_pred = parse_expr(clean_pred, local_dict=local_dict)
                expr_gold = parse_expr(clean_gold, local_dict=local_dict)
            if simplify(expr_pred - expr_gold) == 0:
                return True
            if abs(N(expr_pred) - N(expr_gold)) < 1e-6:
                return True
        except Exception:
            pass

    try:
        return abs(float(clean_pred) - float(clean_gold)) < 1e-6
    except ValueError:
        return False


def generation_bucket(value: Any) -> str:
    try:
        gen = int(value)
    except (TypeError, ValueError):
        return "unknown"
    if gen <= 1:
        return "0-1"
    if gen <= 3:
        return "2-3"
    if gen <= 5:
        return "4-5"
    return "6+"


def load_results(outputs_dir: Path) -> list[dict[str, Any]]:
    files = sorted(glob.glob(str(outputs_dir / "**" / "*_run_*.json"), recursive=True))
    rows = []
    for file_path in files:
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        is_error = file_path.endswith("_error.json")
        meta = data.get("sample_metadata") or {}
        sample_id = data.get("entropymath_id") or data.get("sample_id") or meta.get(
            "entropymath_id"
        ) or data.get("id")
        correct = False if is_error else is_equiv(data.get("final_answer"), data.get("gold_answer"))
        history = data.get("history") or []
        used_tool = any(item.get("role") == "tool" for item in history)
        tool_text = "\n".join(
            str(item.get("content", "")) for item in history if item.get("role") == "tool"
        ).lower()
        tool_error = any(
            marker in tool_text
            for marker in ["error", "traceback", "syntaxerror", "timeout", "no output"]
        )
        rows.append(
            {
                "file": file_path,
                "model_path": str(Path(file_path).parent.relative_to(outputs_dir)),
                "sample_id": str(sample_id),
                "run_idx": data.get("run_idx", 0),
                "correct": bool(correct),
                "final_answer_present": False if is_error else data.get("final_answer") not in (None, ""),
                "gold_answer_present": data.get("gold_answer") not in (None, ""),
                "solver_protocol": data.get("solver_protocol", "tool_assisted"),
                "difficulty_label": meta.get("difficulty_label"),
                "operation": meta.get("operation"),
                "generation": meta.get("generation"),
                "generation_bucket": generation_bucket(meta.get("generation")),
                "used_tool": used_tool,
                "tool_error": tool_error,
                "elapsed_time_sec": data.get("elapsed_time_sec"),
                "token_usage": data.get("token_usage") or {},
            }
        )
    return rows


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def pass_at_k(rows: list[dict[str, Any]]) -> float:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["sample_id"]].append(row["correct"])
    return mean(any(flags) for flags in grouped.values())


def accuracy_at_first(rows: list[dict[str, Any]]) -> float:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["sample_id"]].append(row)
    first_rows = []
    for items in grouped.values():
        first_rows.append(sorted(items, key=lambda item: item.get("run_idx") or 0)[0])
    return mean(row["correct"] for row in first_rows)


def bootstrap_ci(rows: list[dict[str, Any]], metric: str, iters: int, seed: int) -> list[float]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["sample_id"]].append(row)
    problem_groups = list(grouped.values())
    if not problem_groups:
        return [0.0, 0.0]

    rng = random.Random(seed)
    scores = []
    for _ in range(iters):
        sampled_groups = rng.choices(problem_groups, k=len(problem_groups))
        if metric == "pass":
            scores.append(mean(any(row["correct"] for row in group) for group in sampled_groups))
        else:
            first_scores = []
            for group in sampled_groups:
                first = sorted(group, key=lambda item: item.get("run_idx") or 0)[0]
                first_scores.append(first["correct"])
            scores.append(mean(first_scores))
    scores.sort()
    lo = scores[int(0.025 * (len(scores) - 1))]
    hi = scores[int(0.975 * (len(scores) - 1))]
    return [lo, hi]


def summarize_group(rows: list[dict[str, Any]], bootstrap_iters: int, seed: int) -> dict[str, Any]:
    total_runs = len(rows)
    problem_count = len({row["sample_id"] for row in rows})
    accuracy = accuracy_at_first(rows)
    pass_score = pass_at_k(rows)
    return {
        "problem_count": problem_count,
        "run_count": total_runs,
        "accuracy_at_1": accuracy,
        "accuracy_at_1_ci95": bootstrap_ci(rows, "accuracy", bootstrap_iters, seed),
        "pass_at_k": pass_score,
        "pass_at_k_ci95": bootstrap_ci(rows, "pass", bootstrap_iters, seed + 1),
        "consistency_gap": pass_score - accuracy,
        "answer_extraction_failure_rate": mean(
            not row["final_answer_present"] for row in rows
        ),
        "gold_missing_rate": mean(not row["gold_answer_present"] for row in rows),
        "tool_use_rate": mean(row["used_tool"] for row in rows),
        "python_error_rate": mean(row["tool_error"] for row in rows),
    }


def stratify(rows: list[dict[str, Any]], key: str, bootstrap_iters: int, seed: int) -> dict[str, Any]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "unknown")].append(row)
    return {
        group: summarize_group(items, bootstrap_iters, seed)
        for group, items in sorted(grouped.items())
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize EntropyMath eval runs.")
    parser.add_argument("--outputs-dir", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--bootstrap-iters", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260424)
    args = parser.parse_args()

    rows = load_results(args.outputs_dir)
    by_model = defaultdict(list)
    for row in rows:
        by_model[row["model_path"]].append(row)

    summary = {
        "outputs_dir": str(args.outputs_dir),
        "result_file_count": len(rows),
        "model_count": len(by_model),
        "models": {},
    }
    for idx, (model_path, model_rows) in enumerate(sorted(by_model.items())):
        summary["models"][model_path] = {
            "overall": summarize_group(model_rows, args.bootstrap_iters, args.seed + idx),
            "by_difficulty_label": stratify(
                model_rows, "difficulty_label", args.bootstrap_iters, args.seed + idx + 100
            ),
            "by_operation": stratify(
                model_rows, "operation", args.bootstrap_iters, args.seed + idx + 200
            ),
            "by_generation_bucket": stratify(
                model_rows, "generation_bucket", args.bootstrap_iters, args.seed + idx + 300
            ),
            "solver_protocol_counts": dict(Counter(row["solver_protocol"] for row in model_rows)),
        }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    with args.out_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, sort_keys=True)

    print(
        f"Summarized {summary['result_file_count']} result files across "
        f"{summary['model_count']} model directories into {args.out_json}"
    )


if __name__ == "__main__":
    main()
