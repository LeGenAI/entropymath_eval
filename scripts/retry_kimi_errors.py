#!/usr/bin/env python3
"""Retry only the four packaged Kimi K3 errors, without modifying the package."""

import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from math_eval_v7.solvers.direct_solver import DirectSolver, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from prepare_website_results import grade, summarize

MODEL = "moonshotai/kimi-k3"
EXPECTED = {(36, 0), (37, 0), (42, 1), (42, 2)}
SOURCE = Path("results/csat_2026_math/kimi_k3_openrouter/outputs_kimi_k3_csat_math/csat_2026_math_en/direct_no_tool/moonshotai/kimi-k3")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(package):
    source = package / SOURCE
    manifest = read_json(source / "run_manifest.json")
    expected_config = {"model": MODEL, "temperature": 0, "top_p": 1, "max_tokens": 8192,
                       "max_turns": 1, "tool_solver_enabled": False, "sampling_params_locked": False}
    if any(manifest["model"].get(key) != value for key, value in expected_config.items()):
        raise ValueError("Source model settings do not match the approved retry")
    prompt_hash = hashlib.sha256((SYSTEM_PROMPT + "\n\n" + USER_PROMPT_TEMPLATE).encode()).hexdigest()[:16]
    if manifest["prompt_template_sha256_16"] != prompt_hash or manifest["reasoning_effort_override"] is not None:
        raise ValueError("Source prompt or reasoning settings do not match")
    if manifest["solver_protocol"] != "direct_no_tool" or manifest["hard_run_timeout"] != 600:
        raise ValueError("Source protocol/timeout does not match")
    rows = [read_json(path) for path in sorted(source.glob("*_run_*.json"))]
    before = summarize(rows, 46)
    errors = { (row["id"], row["run_idx"]): row for row in rows if row.get("error") or row.get("timeout") }
    if set(errors) != EXPECTED:
        raise ValueError("Source must contain exactly the four approved error attempts")
    hashes = {path.name: digest(path) for path in source.glob("*.json")}
    return source, manifest, rows, errors, hashes, before


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def previous_results(directory, errors, hashes, manifest):
    report = read_json(directory / "retry_manifest.json")
    if (report.get("status") not in ("completed", "incomplete") or not report.get("finished_at_utc")
            or report.get("original_files_unchanged") is not True or report.get("source_sha256") != hashes
            or report.get("model") != MODEL or report.get("dataset") != "csat_2026_math_en"
            or report.get("model_settings") != manifest["model"]
            or report.get("prompt_template_sha256_16") != manifest["prompt_template_sha256_16"]):
        raise ValueError("Previous retry does not match the original experiment")
    attempts = report["attempts"]
    if len(attempts) != 4 or {(a["id"], a["run_idx"]) for a in attempts} != EXPECTED:
        raise ValueError("Previous retry must account for all four original errors")
    results = {}
    for item in attempts:
        if item["status"] == "failed":
            continue
        if item["status"] != "completed":
            raise ValueError("Previous retry has unfinished attempts")
        key = (item["id"], item["run_idx"])
        pid, idx = key
        result = read_json(directory / f"{pid}_run_{idx}.json")
        old = errors[key]
        if (any(result.get(field) != old.get(field) for field in ("id", "run_idx", "problem", "gold_answer"))
                or result.get("error") or result.get("timeout") or not result.get("history")
                or result.get("retry_metadata", {}).get("original_sha256") != hashes[f"{pid}_run_{idx}_error.json"]):
            raise ValueError("Previous successful result does not match its source slot")
        results[key] = result
    return report, results


async def retry(package, dotenv, output, previous_retry_dir=None, provider=None):
    source, manifest, original, errors, hashes, before = validate_source(package)
    previous, results = previous_results(previous_retry_dir, errors, hashes, manifest) if previous_retry_dir else (None, {})
    pending = EXPECTED - results.keys()
    if not pending:
        raise ValueError("No errors remain; no requests sent")
    routing = {"only": [provider], "allow_fallbacks": False, "require_parameters": True} if provider else None
    key = dotenv_values(dotenv).get("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("OPENROUTER_API_KEY is missing or empty; no requests sent")
    if output.resolve().is_relative_to(package.resolve()):
        raise ValueError("Output must be outside the original package")
    output.mkdir(parents=True, exist_ok=False)
    # Archive exact original bytes, including the source error descriptions.
    backup = output / "original_errors"
    backup.mkdir()
    for pid, idx in sorted(EXPECTED):
        name = f"{pid}_run_{idx}_error.json"
        (backup / name).write_bytes((source / name).read_bytes())
    report = {
        "schema_version": 1, "model": MODEL, "dataset": "csat_2026_math_en",
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "status": "running",
        "model_settings": manifest["model"], "prompt_template_sha256_16": manifest["prompt_template_sha256_16"],
        "timeout_seconds": 600, "sdk_max_retries": 0, "concurrency": 2,
        "source_sha256": hashes, "before": before, "attempts": [],
        "provider_routing": routing, "request_count": 0, "reused_count": len(results),
    }
    if previous is not None:
        report["previous_retry_manifest_sha256"] = digest(previous_retry_dir / "retry_manifest.json")
        write_json(output / "previous_retry_manifest.json", previous)
        for item in previous["attempts"]:
            if (item["id"], item["run_idx"]) in results:
                filename = f"{item['id']}_run_{item['run_idx']}.json"
                (output / filename).write_bytes((previous_retry_dir / filename).read_bytes())
                report["attempts"].append({**item, "reused": True})
    write_json(output / "retry_manifest.json", report)
    semaphore = asyncio.Semaphore(2)
    stop = asyncio.Event()
    async with AsyncOpenAI(api_key=key, base_url="https://openrouter.ai/api/v1", max_retries=0, timeout=600) as client:
        async def attempt(pid, idx):
            async with semaphore:
                if stop.is_set():
                    print(f"Skipped PID {pid}, Run {idx + 1}: provider access error", flush=True)
                    report["attempts"].append({"id": pid, "run_idx": idx, "status": "failed", "error_type": "SkippedProviderAccessError"})
                    write_json(output / "retry_manifest.json", report)
                    return
                old = errors[(pid, idx)]
                started = time.monotonic()
                print(f"Starting PID {pid}, Run {idx + 1} (one API request; 600s limit)", flush=True)
                diagnostics = {}
                try:
                    report["request_count"] += 1
                    write_json(output / "retry_manifest.json", report)
                    response = await asyncio.wait_for(client.chat.completions.create(
                        model=MODEL,
                        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                                  {"role": "user", "content": USER_PROMPT_TEMPLATE.format(problem=old["problem"])}],
                        temperature=0, top_p=1, max_tokens=8192, frequency_penalty=0, presence_penalty=0,
                        **({"extra_body": {"provider": routing}} if routing else {}),
                    ), timeout=600)
                    usage = response.usage
                    diagnostics = {"response_id": response.id, "model": response.model,
                                   "provider": getattr(response, "provider", None),
                                   "finish_reason": response.choices[0].finish_reason,
                                   "token_usage": {field: getattr(usage, field, None) for field in ("prompt_tokens", "completion_tokens", "total_tokens")}}
                    if provider and str(diagnostics["provider"]).lower() != provider.split("/")[0].lower():
                        raise ValueError("Returned provider does not match the pinned provider")
                    content = response.choices[0].message.content
                    if not content or not content.strip():
                        raise ValueError("Empty model response")
                    final = DirectSolver._extract_boxed(None, content)
                    result = {field: old[field] for field in ("id", "run_idx", "problem", "gold_answer", "sample_id", "entropymath_id", "sample_metadata") if field in old}
                    result.update({
                        "final_answer": final, "solved": final is not None,
                        "history": [{"role": "assistant", "content": content}],
                        "token_usage": {field: getattr(usage, field, None) for field in ("prompt_tokens", "completion_tokens", "total_tokens")},
                        "elapsed_time_sec": time.monotonic() - started, "solver_protocol": "direct_no_tool",
                        "answer_extraction_status": "boxed_found" if final is not None else "missing_boxed",
                        "response_metadata": diagnostics,
                        "retry_metadata": {"original_file": f"{pid}_run_{idx}_error.json", "original_sha256": hashes[f"{pid}_run_{idx}_error.json"],
                                           "retried_at_utc": datetime.now(timezone.utc).isoformat(), "prompt_template_sha256_16": manifest["prompt_template_sha256_16"]},
                    })
                    if routing:
                        result["retry_metadata"]["provider_routing"] = routing
                        result["retry_metadata"]["provider"] = diagnostics["provider"]
                    filename = f"{pid}_run_{idx}.json"
                    write_json(output / filename, result)
                    results[(pid, idx)] = result
                    status = {"id": pid, "run_idx": idx, "status": "completed", "result_file": filename,
                              "correct": grade(result), "elapsed_time_sec": result["elapsed_time_sec"], "total_tokens": result["token_usage"]["total_tokens"]}
                    print(f"Completed PID {pid}, Run {idx + 1}: correct={status['correct']}, tokens={status['total_tokens']}, {status['elapsed_time_sec']:.1f}s", flush=True)
                except Exception as exc:
                    code = getattr(exc, "status_code", None)
                    if code in (401, 402, 403, 404):
                        stop.set()
                    # Never log provider exception bodies or request headers.
                    status = {"id": pid, "run_idx": idx, "status": "failed", "error_type": type(exc).__name__,
                              "http_status": code, "elapsed_time_sec": time.monotonic() - started}
                    print(f"Failed PID {pid}, Run {idx + 1}: {type(exc).__name__}, HTTP {code}", flush=True)
                status["response_metadata"] = diagnostics
                status["reused"] = False
                report["attempts"].append(status)
                write_json(output / "retry_manifest.json", report)
        await asyncio.gather(*(attempt(pid, idx) for pid, idx in sorted(pending)))
    if any(digest(source / name) != value for name, value in hashes.items()):
        raise RuntimeError("Original files changed during retry")
    merged = [results.get((row["id"], row["run_idx"]), row) for row in original]
    report.update({"status": "completed" if len(results) == 4 else "incomplete", "after": summarize(merged, 46),
                   "finished_at_utc": datetime.now(timezone.utc).isoformat(), "original_files_unchanged": True})
    write_json(output / "retry_manifest.json", report)
    print(json.dumps({"status": report["status"], "completed": len(results), "remaining_errors": report["after"]["error_count"],
                      "correct_runs": report["after"]["correct_runs"], "run_count": 138}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--dotenv", type=Path, default=ROOT / ".env")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--previous-retry-dir", type=Path, help="Reuse completed responses; retry failed slots only")
    parser.add_argument("--provider", choices=["deepinfra/bf16"], help="Pin DeepInfra with no provider fallbacks")
    args = parser.parse_args()
    asyncio.run(retry(args.package.resolve(), args.dotenv.resolve(), args.output.resolve(), args.previous_retry_dir, args.provider))
