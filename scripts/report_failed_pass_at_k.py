#!/usr/bin/env python3
import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path

from summarize_entropymath_results import is_equiv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    root = Path(args.outputs_dir)
    groups = defaultdict(list)
    metadata = {}

    for file_path in glob.glob(str(root / "**" / "*_run_*.json"), recursive=True):
        path = Path(file_path)
        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        model = str(path.parent.relative_to(root))
        sample_id = str(data.get("sample_id", data.get("id")))
        key = (model, sample_id)
        is_error = path.name.endswith("_error.json")
        groups[key].append(
            {
                "run_idx": data.get("run_idx", 0),
                "answer": None if is_error else data.get("final_answer"),
                "correct": False
                if is_error
                else is_equiv(data.get("final_answer"), data.get("gold_answer")),
            }
        )
        metadata[key] = {
            "id": data.get("id"),
            "tokyo_id": (data.get("sample_metadata") or {}).get("ID"),
            "gold": data.get("gold_answer"),
        }

    models = sorted({model for model, _ in groups})
    lines = [
        "# Pass@3 Failed Problems",
        "",
        "Listed problems have no correct answer among their three runs.",
        "`ERROR` means an empty response or request failure.",
        "",
    ]

    for model in models:
        failed = [
            (key, runs)
            for key, runs in groups.items()
            if key[0] == model and not any(run["correct"] for run in runs)
        ]
        failed.sort(key=lambda item: metadata[item[0]]["id"])
        lines.extend([f"## {model}", "", f"Failed: {len(failed)}/30", ""])
        for key, runs in failed:
            meta = metadata[key]
            answers = ", ".join(
                f"run {run['run_idx']}: "
                f"{run['answer'] if run['answer'] is not None else 'ERROR'}"
                for run in sorted(runs, key=lambda item: item["run_idx"])
            )
            lines.append(
                f"- Problem {meta['id']} | {meta['tokyo_id']} | "
                f"gold: `{meta['gold']}` | {answers}"
            )
        lines.append("")

    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved {args.out}")
    for model in models:
        failed_count = sum(
            1
            for key, runs in groups.items()
            if key[0] == model and not any(run["correct"] for run in runs)
        )
        print(f"{model}: {failed_count} failed")


if __name__ == "__main__":
    main()
