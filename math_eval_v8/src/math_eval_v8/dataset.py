from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datasets import load_dataset

from math_eval_v8.types import BenchmarkRow


FORMAL_KEYS = ("formal_statement", "fl_theorem", "theorem", "lean_statement", "statement")
INFORMAL_KEYS = (
    "informal_statement",
    "natural_statement",
    "nl_statement",
    "nl_problem",
    "informal_prefix",
    "problem",
    "question",
)
ID_KEYS = ("problem_id", "uid", "id", "source_id", "name", "problem_name")
HEADER_KEYS = ("header", "lean_header")


def _first(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _to_row(record: dict[str, Any], idx: int) -> BenchmarkRow:
    formal = _first(record, FORMAL_KEYS)
    if not formal:
        raise ValueError(f"row {idx} has no formal statement field")
    if record.get("fl_theorem") and record.get("lean_prefix"):
        formal = str(record["lean_prefix"]).strip() + "\n\n" + str(record["fl_theorem"]).strip()
    problem_id = str(_first(record, ID_KEYS) or idx)
    informal = _first(record, INFORMAL_KEYS)
    header = _first(record, HEADER_KEYS)
    excluded = set(FORMAL_KEYS + INFORMAL_KEYS + ID_KEYS + HEADER_KEYS + ("lean_prefix",))
    return BenchmarkRow(
        problem_id=problem_id,
        formal_statement=str(formal),
        informal_statement=str(informal) if informal is not None else None,
        header=str(header) if header else None,
        split=str(record.get("split")) if record.get("split") else None,
        metadata={key: value for key, value in record.items() if key not in excluded},
    )


def load_benchmark_rows(config: dict[str, Any]) -> list[BenchmarkRow]:
    if config.get("jsonl_path"):
        path = Path(config["jsonl_path"]).expanduser()
        if not path.is_absolute() and config.get("_config_dir"):
            path = Path(config["_config_dir"]) / path
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        dataset = load_dataset(
            config["dataset_path"],
            config.get("dataset_name"),
            data_files=config.get("data_files"),
            split=config.get("split", "test"),
        )
        rows = list(dataset)

    start_idx = int(config.get("start_idx", 0))
    n_problems = config.get("n_problems")
    if start_idx:
        rows = rows[start_idx:]
    for field in config.get("require_nonempty_fields") or []:
        rows = [row for row in rows if str(dict(row).get(field) or "").strip()]
    if config.get("require_compile_success") is not None:
        required = bool(config["require_compile_success"])
        rows = [row for row in rows if bool(dict(row).get("compile_success")) is required]
    if n_problems is not None:
        rows = rows[: int(n_problems)]
    return [_to_row(dict(record), start_idx + idx) for idx, record in enumerate(rows)]
