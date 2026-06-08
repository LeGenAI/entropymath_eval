from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def summarize_records(records: list[dict[str, Any]], *, k: int) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(str(record.get("problem_id")), str(record.get("model")))].append(record)

    rows = []
    by_model: dict[str, list[bool]] = defaultdict(list)
    for (problem_id, model), attempts in sorted(grouped.items()):
        attempts = sorted(attempts, key=lambda item: int(item.get("run_idx", 0)))[:k]
        passed = any(bool((item.get("verifier") or {}).get("complete")) for item in attempts)
        oracle_values = [
            bool((item.get("oracle_alignment") or {}).get("oracle_aligned_pass"))
            for item in attempts
            if item.get("oracle_alignment") is not None
        ]
        proof_path_scores = [
            float((item.get("oracle_alignment") or {}).get("proof_path_alignment_score"))
            for item in attempts
            if (item.get("oracle_alignment") or {}).get("proof_path_alignment_score") is not None
        ]
        oracle_passed = any(oracle_values) if oracle_values else None
        by_model[model].append(passed)
        rows.append(
            {
                "problem_id": problem_id,
                "model": model,
                "attempts": len(attempts),
                "pass_at_k": passed,
                "oracle_aligned_pass_at_k": oracle_passed,
                "oracle_proof_path_alignment_max": max(proof_path_scores) if proof_path_scores else None,
            }
        )

    models = []
    for model, values in sorted(by_model.items()):
        model_records = [record for record in records if str(record.get("model")) == model]
        model_proof_path_scores = [
            float((record.get("oracle_alignment") or {}).get("proof_path_alignment_score"))
            for record in model_records
            if (record.get("oracle_alignment") or {}).get("proof_path_alignment_score") is not None
        ]
        models.append(
            {
                "model": model,
                "rows": len(values),
                "passed": sum(1 for value in values if value),
                "pass_at_k": sum(1 for value in values if value) / len(values) if values else 0.0,
                "attempt_errors": sum(1 for record in model_records if record.get("error")),
                "oracle_judged_attempts": sum(1 for record in model_records if record.get("oracle_alignment") is not None),
                "oracle_aligned_attempts": sum(
                    1 for record in model_records if (record.get("oracle_alignment") or {}).get("oracle_aligned_pass")
                ),
                "avg_oracle_proof_path_alignment": (
                    sum(model_proof_path_scores) / len(model_proof_path_scores)
                    if model_proof_path_scores
                    else None
                ),
            }
        )
    return {"k": k, "models": models, "rows": rows}


def summarize_jsonl(input_path: Path, output_path: Path, *, k: int) -> dict[str, Any]:
    records = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = summarize_records(records, k=k)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary
