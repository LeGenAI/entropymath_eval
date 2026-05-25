#!/usr/bin/env python3
"""Prepare the frozen EntropyMath model-evaluation sample for math_eval_v7.

The paper-facing protocol should evaluate the public frozen 120-row sample, not
the older mixed pilot outputs. This script converts the release CSV into a local
JSONL dataset that Hugging Face `load_dataset("json", ...)` can read and writes
a small manifest documenting the split composition.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_CSV = Path(
    "/Users/imds/Desktop/icml_2026_entropymath/"
    "repo/data/public/evaluation_samples/model_eval_stratified_120.csv"
)
DEFAULT_OUTPUT_JSONL = Path("data/entropymath_generated_v1_model_eval_120.jsonl")
DEFAULT_OUTPUT_MANIFEST = Path(
    "data/entropymath_generated_v1_model_eval_120_manifest.json"
)


def _maybe_number(value: str) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return value


def _json_list(value: str) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        pass
    return [value]


def convert_row(row: dict[str, str], row_index: int) -> dict[str, Any]:
    """Map the public CSV schema to a local eval schema.

    `question` and `answer` are the keys consumed by the existing runner. The
    EntropyMath-specific fields are preserved for stratified analysis and audit.
    """

    return {
        "id": row.get("id") or f"entropymath_{row_index:03d}",
        "entropymath_id": row.get("id") or f"entropymath_{row_index:03d}",
        "question": row.get("statement", ""),
        "statement": row.get("statement", ""),
        "answer": row.get("answer", ""),
        "solution": row.get("solution", ""),
        "verification_code": row.get("verification_code", ""),
        "operation": row.get("operation", ""),
        "difficulty": _maybe_number(row.get("difficulty", "")),
        "difficulty_label": row.get("difficulty_label", ""),
        "generation": _maybe_number(row.get("generation", "")),
        "source_run": row.get("source_run", ""),
        "source_file": row.get("source_file", ""),
        "source_slot": _maybe_number(row.get("source_slot", "")),
        "parent_ids": _json_list(row.get("parent_ids", "")),
        "ancestor_ids": _json_list(row.get("ancestor_ids", "")),
        "statement_sha256": row.get("statement_sha256", ""),
        "answer_sha256": row.get("answer_sha256", ""),
        "sample_index": row_index,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert EntropyMath frozen 120-row CSV to local JSONL."
    )
    parser.add_argument("--source-csv", type=Path, default=DEFAULT_SOURCE_CSV)
    parser.add_argument("--output-jsonl", type=Path, default=DEFAULT_OUTPUT_JSONL)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_OUTPUT_MANIFEST)
    args = parser.parse_args()

    if not args.source_csv.exists():
        raise FileNotFoundError(f"Source CSV not found: {args.source_csv}")

    with args.source_csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    converted = [convert_row(row, idx) for idx, row in enumerate(rows)]
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("w", encoding="utf-8") as f:
        for item in converted:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    difficulty_counts = Counter(item.get("difficulty_label") for item in converted)
    operation_counts = Counter(item.get("operation") for item in converted)
    generation_counts = Counter(str(item.get("generation")) for item in converted)
    statement_hashes = [item.get("statement_sha256") for item in converted]

    manifest = {
        "name": "entropymath_generated_v1_model_eval_120",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_csv": str(args.source_csv),
        "output_jsonl": str(args.output_jsonl),
        "row_count": len(converted),
        "unique_statement_sha256": len(set(statement_hashes)),
        "difficulty_label_counts": dict(sorted(difficulty_counts.items())),
        "operation_counts": dict(sorted(operation_counts.items())),
        "generation_counts": dict(sorted(generation_counts.items())),
        "intended_use": (
            "Frozen paper-facing model-evaluation sample for EntropyMath-"
            "Generated-v1. Legacy pilot outputs should not be mixed into main "
            "model-evaluation evidence."
        ),
        "primary_protocol": {
            "solver": "direct_no_tool",
            "metric": "accuracy@1",
            "secondary_metrics": ["pass@3", "consistency_gap"],
            "temperature": "0 when accepted by provider; otherwise provider minimum",
        },
    }

    with args.manifest.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, sort_keys=True)

    print(f"Wrote {len(converted)} rows to {args.output_jsonl}")
    print(f"Wrote manifest to {args.manifest}")


if __name__ == "__main__":
    main()
