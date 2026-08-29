import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import yaml


DEFAULT_COMP = "tokyo_math_hf_private"


def discover_models(models_dir):
    return sorted(path.stem for path in Path(models_dir).glob("*.yaml"))


def parse_csv(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]

def load_dotenv(path):
    env = {}
    path = Path(path)
    if not path.exists():
        return env
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env

def env_value(name, dotenv_values):
    return os.environ.get(name) or dotenv_values.get(name)

def is_placeholder_secret(value):
    if not value:
        return True
    lowered = value.lower()
    return lowered.startswith("your_") or "your_" in lowered or lowered.endswith("_key")

def required_env_placeholder(value):
    if not isinstance(value, str):
        return None
    value = value.strip().strip('"').strip("'")
    if value.startswith("${") and value.endswith("}"):
        return value[2:-1]
    return None

def resolved_config_value(value, dotenv_values):
    env_name = required_env_placeholder(value)
    return env_value(env_name, dotenv_values) if env_name else value

def localish_host(hostname):
    if not hostname:
        return True
    host = hostname.lower()
    return (
        host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        or host.startswith("10.")
        or host.startswith("192.168.")
        or host.startswith("172.16.")
        or host.startswith("172.17.")
        or host.startswith("172.18.")
        or host.startswith("172.19.")
        or host.startswith("172.2")
        or host.startswith("172.30.")
        or host.startswith("172.31.")
    )

def skip_reason_for_model(model_path, dotenv_values, include_local):
    with model_path.open() as f:
        config = yaml.safe_load(f) or {}

    for field_name in ("model", "base_url", "api_key"):
        env_name = required_env_placeholder(config.get(field_name))
        if env_name and is_placeholder_secret(env_value(env_name, dotenv_values)):
            return f"missing env {env_name}"

    base_url = resolved_config_value(config.get("base_url"), dotenv_values)
    if not base_url:
        if config.get("api_key") in (None, "not-needed", "dummy"):
            return "no base_url; would use local default endpoint"
        return None

    parsed = urlparse(str(base_url))
    if localish_host(parsed.hostname) and not include_local:
        return f"local/private endpoint {parsed.hostname}; pass --include-local to run"

    return None


def main():
    parser = argparse.ArgumentParser(description="Run the Tokyo math evaluation across model configs.")
    parser.add_argument("--comp", default=DEFAULT_COMP, help="Competition config name.")
    parser.add_argument("--models-dir", default="configs/models", help="Directory containing model YAML configs.")
    parser.add_argument("--models", default=None, help="Comma-separated model config names to run. Defaults to all YAML files.")
    parser.add_argument("--exclude", default=None, help="Comma-separated model config names to skip.")
    parser.add_argument("--solver", choices=["direct", "tool"], default="direct", help="Solver protocol.")
    parser.add_argument("--n-repeats", type=int, default=1, help="Repeats per problem.")
    parser.add_argument("--max-problems", type=int, default=None, help="Optional smoke-test limit.")
    parser.add_argument("--dotenv", default=".env", help="Dotenv file for HF/provider tokens.")
    parser.add_argument("--output", default="outputs", help="Output directory for evaluations.")
    parser.add_argument("--request-timeout", type=float, default=None, help="Per-request API timeout in seconds.")
    parser.add_argument("--per-model-timeout", type=float, default=None, help="Optional maximum seconds for each model config. Defaults to no model-wide timeout.")
    parser.add_argument("--max-tokens-override", type=int, default=None, help="Override max_tokens for every model.")
    parser.add_argument("--reasoning-effort-override", default=None, help="Override reasoning effort for every model.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop after the first model failure.")
    parser.add_argument("--include-local", action="store_true", help="Also run localhost/private-network model endpoints.")
    parser.add_argument("--no-preflight", action="store_true", help="Disable model config preflight skipping.")
    parser.add_argument("--resume", action="store_true", help="Skip individual runs whose result or error file already exists.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    models_dir = repo_root / args.models_dir
    selected = parse_csv(args.models) if args.models else discover_models(models_dir)
    excluded = set(parse_csv(args.exclude))
    models = [model for model in selected if model not in excluded]
    dotenv_values = load_dotenv(args.dotenv) if args.dotenv else {}

    if not models:
        print("No models selected after applying --models/--exclude.", flush=True)
        return

    summary = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "finished_at_utc": None,
        "competition": args.comp,
        "solver": args.solver,
        "n_repeats": args.n_repeats,
        "max_problems": args.max_problems,
        "models_total": len(models),
        "runs": [],
    }

    summary_dir = repo_root / args.output / args.comp / "_batch"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"all_models_{args.solver}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    for index, model in enumerate(models, start=1):
        print(f"\n[{index}/{len(models)}] Running {model}", flush=True)
        model_path = models_dir / f"{model}.yaml"
        if not args.no_preflight:
            skip_reason = skip_reason_for_model(model_path, dotenv_values, args.include_local)
            if skip_reason:
                print(f"[{model}] skipped: {skip_reason}", flush=True)
                summary["runs"].append(
                    {
                        "model_config": model,
                        "started_at_utc": datetime.now(timezone.utc).isoformat(),
                        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                        "returncode": None,
                        "status": "skipped",
                        "skip_reason": skip_reason,
                    }
                )
                with summary_path.open("w") as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False)
                continue

        cmd = [
            sys.executable,
            "scripts/run.py",
            "--comp",
            args.comp,
            "--model",
            model,
            "--solver",
            args.solver,
            "--n_repeats",
            str(args.n_repeats),
            "--output",
            args.output,
        ]
        if args.dotenv and Path(args.dotenv).exists():
            cmd.extend(["--dotenv", args.dotenv])
        if args.max_problems is not None:
            cmd.extend(["--max-problems", str(args.max_problems)])
        if args.resume:
            cmd.append("--resume")
        request_timeout = args.request_timeout if args.request_timeout is not None else 120
        cmd.extend(["--request-timeout", str(request_timeout)])
        if args.max_tokens_override is not None:
            cmd.extend(["--max-tokens-override", str(args.max_tokens_override)])
        if args.reasoning_effort_override is not None:
            cmd.extend(["--reasoning-effort-override", args.reasoning_effort_override])

        started = datetime.now(timezone.utc)
        run = {
            "model_config": model,
            "started_at_utc": started.isoformat(),
            "finished_at_utc": None,
            "returncode": None,
            "status": "running",
        }
        summary["runs"].append(run)

        child_env = os.environ.copy()
        hf_home = repo_root / ".cache" / "huggingface"
        hf_home.mkdir(parents=True, exist_ok=True)
        child_env.setdefault("HF_HOME", str(hf_home))
        child_env.setdefault("HF_DATASETS_CACHE", str(hf_home / "datasets"))

        try:
            completed = subprocess.run(
                cmd,
                cwd=repo_root,
                env=child_env,
                timeout=args.per_model_timeout,
            )
            returncode = completed.returncode
            status = "success" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            returncode = None
            status = "timeout"
            print(f"[{model}] timed out after {args.per_model_timeout} seconds", flush=True)

        finished = datetime.now(timezone.utc)
        run["finished_at_utc"] = finished.isoformat()
        run["elapsed_seconds"] = round((finished - started).total_seconds(), 3)
        run["returncode"] = returncode
        run["status"] = status

        with summary_path.open("w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        if status != "success":
            print(f"[{model}] {status} with exit code {returncode}", flush=True)
            if args.stop_on_error:
                break

    summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nBatch summary saved to {summary_path}", flush=True)


if __name__ == "__main__":
    main()
