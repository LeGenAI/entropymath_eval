#!/usr/bin/env python3
import argparse
import glob
import json
from pathlib import Path


NAMES = {
    "deprk58vp9q3z6g": "KT Mi:dm 2.0",
    "LGAI-EXAONE/K-EXAONE-236B-A23B": "K-EXAONE",
    "upstage/solar-pro-3": "Solar Pro 3",
    "openai/gpt-5.5": "GPT-5.5",
    "anthropic/claude-opus-4.8": "Opus 4.8",
    "google/gemini-3.5-flash": "Gemini 3.5 Flash",
    "deepseek/deepseek-v4-pro": "DeepSeek V4 Pro",
}

CONFIG_TO_MODEL = {
    "hosted_kt_midm": "deprk58vp9q3z6g",
    "friendli_k_exaone": "LGAI-EXAONE/K-EXAONE-236B-A23B",
    "openrouter_solar_pro_3": "upstage/solar-pro-3",
    "openrouter_gpt_5_5": "openai/gpt-5.5",
    "openrouter_claude_opus_4_8": "anthropic/claude-opus-4.8",
    "openrouter_gemini_3_5_flash": "google/gemini-3.5-flash",
    "openrouter_deepseek_v4_pro": "deepseek/deepseek-v4-pro",
}


def duration(seconds):
    seconds = round(seconds)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs-dir", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    root = Path(args.outputs_dir)
    summary = json.loads(Path(args.summary).read_text())
    batch = json.loads(Path(args.batch).read_text())
    elapsed = {
        CONFIG_TO_MODEL[run["model_config"]]: run["elapsed_seconds"]
        for run in batch["runs"]
    }

    tokens = {}
    for file_path in glob.glob(str(root / "**" / "*_run_[0-9].json"), recursive=True):
        data = json.loads(Path(file_path).read_text())
        model = str(Path(file_path).parent.relative_to(root))
        usage = data.get("token_usage") or {}
        totals = tokens.setdefault(model, {"input": 0, "output": 0, "total": 0, "reported_runs": 0})
        totals["input"] += usage.get("prompt_tokens") or 0
        totals["output"] += usage.get("completion_tokens") or 0
        totals["total"] += usage.get("total_tokens") or 0
        totals["reported_runs"] += 1

    rows = []
    for model, values in summary["models"].items():
        overall = values["overall"]
        usage = tokens.get(model, {"input": 0, "output": 0, "total": 0, "reported_runs": 0})
        rows.append(
            {
                "model": NAMES.get(model, model),
                "pass1": overall["accuracy_at_1"],
                "pass3": overall["pass_at_k"],
                "elapsed_seconds": elapsed[model],
                **usage,
            }
        )
    rows.sort(key=lambda row: (-row["pass3"], -row["pass1"]))

    lines = [
        "# Model Metrics",
        "",
        "| Model | Pass@1 | Pass@3 | Wall-clock time | Input tokens | Output tokens | Total tokens | Token-reported runs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['model']} | {row['pass1'] * 100:.2f}% | {row['pass3'] * 100:.2f}% | "
            f"{duration(row['elapsed_seconds'])} | {row['input']:,} | {row['output']:,} | "
            f"{row['total']:,} | {row['reported_runs']}/90 |"
        )
    lines.extend(
        [
            "",
            "- Pass@1 and Pass@3 count error/empty-response runs as incorrect.",
            "- Wall-clock time includes rate-limit waits, empty responses, and request overhead.",
            "- Token totals include successful runs where the provider returned token usage.",
        ]
    )
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
