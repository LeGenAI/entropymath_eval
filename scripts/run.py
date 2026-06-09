import argparse
import yaml
import json
import os
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from tqdm import tqdm
from datasets import load_dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from math_eval_v7.solvers.direct_solver import DirectSolver
from math_eval_v7.solvers.tool_solver import ToolSolver

def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def load_dotenv(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"dotenv file not found: {path}")
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

def resolve_config_path(config_dir, value):
    path = Path(value)
    if path.exists():
        return path
    if path.suffix == ".yaml":
        candidate = Path(config_dir) / path
    else:
        candidate = Path(config_dir) / f"{value}.yaml"
    return candidate

def sha256_short(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def infer_provider(model_config):
    api_type = model_config.get("api_type")
    base_url = (model_config.get("base_url") or "").lower()
    model = (model_config.get("model") or "").lower()
    if api_type == "clova" or "clova" in base_url:
        return "clova"
    if "openrouter" in base_url or model.startswith("openrouter/"):
        return "openrouter"
    if "friendli" in base_url:
        return "friendli"
    if "upstage" in base_url or "solar" in model:
        return "upstage"
    if "localhost" in base_url or "127.0.0.1" in base_url:
        return "local"
    return api_type or "openai_compatible"

def default_api_key_for_provider(model_config):
    if model_config.get("api_key"):
        return model_config.get("api_key")
    provider = infer_provider(model_config)
    env_by_provider = {
        "openrouter": "OPENROUTER_API_KEY",
        "friendli": "FRIENDLI_API_KEY",
        "upstage": "UPSTAGE_API_KEY",
        "clova": "CLOVA_STUDIO_API_KEY",
    }
    env_name = env_by_provider.get(provider)
    return os.environ.get(env_name) if env_name else None

def sanitized_model_summary(model_config):
    return {
        "model": model_config.get("model"),
        "provider": infer_provider(model_config),
        "api_type": model_config.get("api_type", "openai"),
        "temperature": model_config.get("temperature"),
        "top_p": model_config.get("top_p"),
        "max_tokens": model_config.get("max_tokens"),
        "max_turns": model_config.get("max_turns"),
        "sampling_params_locked": model_config.get("sampling_params_locked", False),
        "tool_solver_enabled": model_config.get("tool_solver_enabled", True),
    }

def resolve_env_placeholder(value, field_name):
    if not isinstance(value, str):
        return value
    if not (value.startswith("${") and value.endswith("}")):
        return value
    env_name = value[2:-1]
    resolved = os.environ.get(env_name)
    if not resolved:
        raise RuntimeError(f"Environment variable is not set for {field_name}: {env_name}")
    return resolved

def get_problem_text(item):
    return (
        item.get("question")
        or item.get("statement")
        or item.get("Question")
        or item.get("problem")
    )

def get_gold_answer(item):
    return (
        item.get("answer")
        or item.get("Answer")
        or item.get("gold_answer")
        or item.get("solution")
        or item.get("Solution")
    )

def get_sample_metadata(item):
    excluded = {
        "question",
        "Question",
        "problem",
        "statement",
        "answer",
        "Answer",
        "gold_answer",
        "solution",
        "Solution",
        "verification_code",
    }
    return {key: value for key, value in item.items() if key not in excluded}

def build_dataset_load_kwargs(comp_config):
    kwargs = {}
    hf_token_env = comp_config.get("hf_token_env")
    if hf_token_env:
        hf_token = os.environ.get(hf_token_env)
        if not hf_token:
            raise RuntimeError(f"Environment variable is not set for private HF dataset: {hf_token_env}")
        kwargs["token"] = hf_token
    if "trust_remote_code" in comp_config:
        kwargs["trust_remote_code"] = comp_config["trust_remote_code"]
    return kwargs

def load_hf_dataset(comp_config, split):
    data_files = comp_config.get("data_files")
    load_kwargs = build_dataset_load_kwargs(comp_config)
    try:
        return load_dataset(
            comp_config["dataset_path"],
            comp_config.get("dataset_name"),
            data_files=data_files,
            split=split,
            **load_kwargs,
        )
    except TypeError as exc:
        if "token" not in load_kwargs:
            raise
        legacy_kwargs = dict(load_kwargs)
        legacy_kwargs["use_auth_token"] = legacy_kwargs.pop("token")
        return load_dataset(
            comp_config["dataset_path"],
            comp_config.get("dataset_name"),
            data_files=data_files,
            split=split,
            **legacy_kwargs,
        )

def write_manifest(output_dir, manifest):
    with open(os.path.join(output_dir, "run_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, sort_keys=True)

def main():
    parser = argparse.ArgumentParser(description="Run Math Eval V7")
    parser.add_argument("--comp", type=str, required=True, help="Path to competition config (relative to configs/competitions)")
    parser.add_argument("--model", type=str, required=True, help="Path to model config (relative to configs/models)")
    parser.add_argument("--output", type=str, default="outputs", help="Output directory")
    parser.add_argument("--n_repeats", type=int, default=1, help="Number of repeats per problem")
    parser.add_argument("--solver", choices=["tool", "direct"], default="tool", help="Solver protocol")
    parser.add_argument("--temperature-override", type=float, default=None, help="Override model config temperature")
    parser.add_argument("--model-id-override", type=str, default=None, help="Override provider model id without creating a new credential config")
    parser.add_argument("--api-key-env", type=str, default=None, help="Read provider API key from this environment variable")
    parser.add_argument("--dotenv", type=str, default=None, help="Load environment variables from a dotenv file before config overrides")
    parser.add_argument("--request-timeout", type=float, default=None, help="Per-request API timeout in seconds")
    parser.add_argument("--max-tokens-override", type=int, default=None, help="Override max_tokens for the model request")
    parser.add_argument("--reasoning-effort-override", type=str, default=None, help="Override reasoning effort; use 'none' to remove inherited effort")
    parser.add_argument("--max-problems", type=int, default=None, help="Optional dry-run limit after competition slicing")
    parser.add_argument("--resume", action="store_true", help="Skip runs that already have a result or error file.")
    args = parser.parse_args()

    # Load configs
    comp_config_path = resolve_config_path("configs/competitions", args.comp)
    model_config_path = resolve_config_path("configs/models", args.model)
    if args.dotenv:
        load_dotenv(args.dotenv)
    
    comp_config = load_config(comp_config_path)
    model_config = load_config(model_config_path)
    for field_name in ("model", "base_url", "api_key"):
        if field_name in model_config:
            model_config[field_name] = resolve_env_placeholder(model_config[field_name], field_name)
    if "api_key" not in model_config:
        default_api_key = default_api_key_for_provider(model_config)
        if default_api_key:
            model_config["api_key"] = default_api_key
    if args.model_id_override:
        model_config["model"] = args.model_id_override
    if args.api_key_env:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"Environment variable is not set: {args.api_key_env}")
        model_config["api_key"] = api_key
    if args.temperature_override is not None:
        model_config["temperature"] = args.temperature_override
    if args.request_timeout is not None:
        model_config["request_timeout"] = args.request_timeout
    if args.max_tokens_override is not None:
        model_config["max_tokens"] = args.max_tokens_override
    if args.reasoning_effort_override is not None:
        if args.reasoning_effort_override.lower() == "none":
            model_config.pop("reasoning_effort", None)
            model_config.pop("effort", None)
        else:
            model_config["reasoning_effort"] = args.reasoning_effort_override
            model_config.pop("effort", None)
    model_config["tool_solver_enabled"] = args.solver == "tool"
    print(f"Loaded model config: {sanitized_model_summary(model_config)}")

    # Load dataset
    print(f"Loading dataset: {comp_config['dataset_path']}...")
    try:
        dataset = load_hf_dataset(comp_config, comp_config.get('subset', 'test'))
    except ValueError:
        print("Split 'test' not found, trying 'train'...")
        dataset = load_hf_dataset(comp_config, 'train')
    
    # Limit problems if specified (support optional start_idx)
    start_idx = comp_config.get('start_idx', 0)
    if 'n_problems' in comp_config:
        end_idx = min(len(dataset), start_idx + comp_config['n_problems'])
        dataset = dataset.select(range(start_idx, end_idx))
    if args.max_problems is not None:
        dataset = dataset.select(range(0, min(len(dataset), args.max_problems)))

    # Initialize solver
    solver = DirectSolver(model_config) if args.solver == "direct" else ToolSolver(model_config)

    # Prepare output directory
    comp_name = comp_config.get('name', args.comp)
    solver_name = "direct_no_tool" if args.solver == "direct" else "tool_assisted"
    output_dir = os.path.join(args.output, comp_name, solver_name, model_config['model'])
    os.makedirs(output_dir, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    prompt_material = getattr(solver, "prompt_template", None) or (
        getattr(solver, "system_prompt", "") + "\n\n" + str(comp_config.get("instruction", ""))
    )
    manifest = {
        "started_at_utc": started_at,
        "finished_at_utc": None,
        "competition": {
            "name": comp_name,
            "config_path": str(comp_config_path),
            "dataset_path": comp_config.get("dataset_path"),
            "data_files": comp_config.get("data_files"),
            "hf_token_env": comp_config.get("hf_token_env"),
            "subset": comp_config.get("subset", "test"),
            "start_idx": start_idx,
            "n_rows_loaded": len(dataset),
        },
        "model": sanitized_model_summary(model_config),
        "model_config_path": str(model_config_path),
        "model_id_override": args.model_id_override,
        "api_key_env": args.api_key_env,
        "reasoning_effort_override": args.reasoning_effort_override,
        "solver_protocol": solver_name,
        "n_repeats": args.n_repeats,
        "prompt_template_sha256_16": sha256_short(prompt_material),
        "parser_version": "boxed_extractor_v1",
        "grader_version": "sympy_equivalence_v1",
        "result_count": 0,
        "error_count": 0,
    }
    write_manifest(output_dir, manifest)

    # Run evaluation
    results = []
    error_count = 0
    for i, item in tqdm(enumerate(dataset), total=len(dataset)):
        global_idx = start_idx + i
        problem_text = get_problem_text(item)
        if not problem_text:
            print(f"Skipping problem {i}: No question found.")
            continue
            
        print(f"Solving problem {i}...")
        
        for run_idx in range(args.n_repeats):
            result_path = os.path.join(output_dir, f"{global_idx}_run_{run_idx}.json")
            error_path = os.path.join(output_dir, f"{global_idx}_run_{run_idx}_error.json")
            if args.resume and (os.path.exists(result_path) or os.path.exists(error_path)):
                print(f"Skipping existing problem {global_idx}, run {run_idx}.")
                continue
            try:
                result = solver.solve(problem_text)
                result['id'] = global_idx
                result['sample_id'] = item.get('id') or item.get('entropymath_id') or global_idx
                result['entropymath_id'] = item.get('entropymath_id') or item.get('id')
                result['run_idx'] = run_idx
                result['solver_protocol'] = solver_name
                result['gold_answer'] = get_gold_answer(item)
                result['sample_metadata'] = get_sample_metadata(item)
                result['run_metadata'] = {
                    "model": sanitized_model_summary(model_config),
                    "prompt_template_sha256_16": manifest["prompt_template_sha256_16"],
                    "parser_version": manifest["parser_version"],
                    "grader_version": manifest["grader_version"],
                    "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                }
                
                # Save individual result
                with open(result_path, 'w') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                if os.path.exists(error_path):
                    os.unlink(error_path)
                
                results.append(result)
            except Exception as e:
                print(f"Error solving problem {global_idx}, run {run_idx}: {e}")
                error_count += 1
                # Save error state
                error_result = {
                    "id": global_idx,
                    "sample_id": item.get('id') or item.get('entropymath_id') or global_idx,
                    "entropymath_id": item.get('entropymath_id') or item.get('id'),
                    "run_idx": run_idx,
                    "problem": problem_text,
                    "error": str(e),
                    "solved": False,
                    "final_answer": None,
                    "gold_answer": get_gold_answer(item),
                    "solver_protocol": solver_name,
                    "sample_metadata": get_sample_metadata(item),
                }
                with open(error_path, 'w') as f:
                    json.dump(error_result, f, indent=2, ensure_ascii=False)
                continue

    # Calculate accuracy (simple check)
    correct = 0
    for r in results:
        if r['final_answer'] and r['gold_answer']:
            # Very basic check, ideally needs rigorous grading
            if r['final_answer'].strip() == str(r['gold_answer']).strip():
                correct += 1
    
    print(f"Evaluation Complete.")
    if results:
        print(f"Approximate exact-string accuracy: {correct}/{len(results)} ({correct/len(results)*100:.2f}%)")
        print("Use scripts/summarize_entropymath_results.py for paper metrics and SymPy-based regrading.")
    else:
        print("No results to score (all problems skipped).")
    manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["result_count"] = len(results)
    manifest["error_count"] = error_count
    write_manifest(output_dir, manifest)
    print(f"Results saved to {output_dir}")
    if not results and len(dataset) > 0:
        sys.exit(2)

if __name__ == "__main__":
    main()
