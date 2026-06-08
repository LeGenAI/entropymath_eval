from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one v8 benchmark over a model panel")
    parser.add_argument("--bench", required=True)
    parser.add_argument("--panel", required=True)
    parser.add_argument("--output", default="outputs")
    parser.add_argument("--n-repeats", type=int, default=1)
    parser.add_argument("--max-problems", type=int, default=None)
    parser.add_argument("--lean-timeout", type=float, default=None)
    parser.add_argument("--lean-project-path", default=None)
    parser.add_argument("--repair-turns", type=int, default=0)
    parser.add_argument("--keep-going", action="store_true", default=True)
    args = parser.parse_args()

    panel = load_yaml(args.panel)
    models = panel.get("models") or []
    if not models:
        raise RuntimeError(f"no models found in panel: {args.panel}")

    for model_path in models:
        resolved_model = Path(model_path)
        if not resolved_model.is_absolute():
            resolved_model = (ROOT / resolved_model).resolve()
        cmd = [
            sys.executable,
            str(ROOT / "scripts/run.py"),
            "--bench",
            args.bench,
            "--model",
            str(resolved_model),
            "--output",
            args.output,
            "--n-repeats",
            str(args.n_repeats),
            "--repair-turns",
            str(args.repair_turns),
        ]
        if args.max_problems is not None:
            cmd.extend(["--max-problems", str(args.max_problems)])
        if args.lean_timeout is not None:
            cmd.extend(["--lean-timeout", str(args.lean_timeout)])
        if args.lean_project_path is not None:
            cmd.extend(["--lean-project-path", args.lean_project_path])
        completed = subprocess.run(cmd, cwd=str(ROOT), check=False)
        if completed.returncode != 0 and not args.keep_going:
            raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
