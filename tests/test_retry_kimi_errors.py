import asyncio
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("retry_kimi_errors", ROOT / "scripts/retry_kimi_errors.py")
retry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retry)


class RetryTests(unittest.TestCase):
    def test_one_request_per_error_without_touching_normal_attempts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "package"
            source = package / retry.SOURCE
            source.mkdir(parents=True)
            rows = []
            for pid in range(46):
                for idx in range(3):
                    row = {"id": pid, "run_idx": idx, "problem": f"Original {pid}", "gold_answer": "1", "final_answer": "1"}
                    is_error = (pid, idx) in retry.EXPECTED
                    if is_error:
                        row.update(error="original timeout", final_answer=None)
                    rows.append(row)
                    filename = f"{pid}_run_{idx}{'_error' if is_error else ''}.json"
                    (source / filename).write_text(json.dumps(row))
            errors = {(row["id"], row["run_idx"]): row for row in rows if row.get("error")}
            hashes = {path.name: retry.digest(path) for path in source.glob("*.json")}
            manifest = {"model": {"model": retry.MODEL}, "prompt_template_sha256_16": "test-hash"}
            calls = []

            class Client:
                def __init__(self, **options):
                    self.options = options
                    self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.complete))

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

                async def complete(self, **kwargs):
                    calls.append(kwargs)
                    return SimpleNamespace(id="test-response", model=retry.MODEL, provider="DeepInfra",
                        choices=[SimpleNamespace(message=SimpleNamespace(content=r"\boxed{1}"), finish_reason="stop")],
                        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30))

            output = root / "retry"
            with patch.object(retry, "validate_source", return_value=(source, manifest, rows, errors, hashes, retry.summarize(rows, 46))), \
                 patch.object(retry, "dotenv_values", return_value={"OPENROUTER_API_KEY": "fake-test-key"}), \
                 patch.object(retry, "AsyncOpenAI", Client), contextlib.redirect_stdout(io.StringIO()):
                asyncio.run(retry.retry(package, root / ".env", output))
            self.assertEqual(len(calls), 4)
            for call in calls:
                self.assertEqual(call["model"], retry.MODEL)
                self.assertEqual((call["temperature"], call["top_p"], call["max_tokens"]), (0, 1, 8192))
                self.assertNotIn("tools", call)
                self.assertEqual(call["messages"][0]["content"], retry.SYSTEM_PROMPT)
            self.assertEqual(sorted(call["messages"][1]["content"] for call in calls),
                             sorted(retry.USER_PROMPT_TEMPLATE.format(problem=errors[key]["problem"]) for key in retry.EXPECTED))
            self.assertEqual(hashes, {path.name: retry.digest(path) for path in source.glob("*.json")})
            report = retry.read_json(output / "retry_manifest.json")
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["after"]["run_count"], 138)
            self.assertEqual(report["after"]["error_count"], 0)
            self.assertEqual(report["sdk_max_retries"], 0)
            self.assertNotIn("fake-test-key", (output / "retry_manifest.json").read_text())
            self.assertEqual(len(list(output.glob("*_run_*.json"))), 4)
            self.assertEqual(len(list((output / "original_errors").glob("*.json"))), 4)

            # Resume a batch with only PID 37/run 0 recovered. Never request it again.
            for item in report["attempts"]:
                if (item["id"], item["run_idx"]) != (37, 0):
                    item["status"] = "failed"
            report["status"] = "incomplete"
            retry.write_json(output / "retry_manifest.json", report)
            calls.clear()
            resumed = root / "deepinfra"
            with patch.object(retry, "validate_source", return_value=(source, manifest, rows, errors, hashes, retry.summarize(rows, 46))), \
                 patch.object(retry, "dotenv_values", return_value={"OPENROUTER_API_KEY": "fake-test-key"}), \
                 patch.object(retry, "AsyncOpenAI", Client), contextlib.redirect_stdout(io.StringIO()):
                asyncio.run(retry.retry(package, root / ".env", resumed, output, "deepinfra/bf16"))
            self.assertEqual(len(calls), 3)
            self.assertEqual(sorted(call["messages"][1]["content"] for call in calls),
                             sorted(retry.USER_PROMPT_TEMPLATE.format(problem=errors[key]["problem"]) for key in retry.EXPECTED - {(37, 0)}))
            for call in calls:
                self.assertEqual(call["extra_body"], {"provider": {"only": ["deepinfra/bf16"], "allow_fallbacks": False, "require_parameters": True}})
                self.assertEqual((call["temperature"], call["top_p"], call["max_tokens"]), (0, 1, 8192))
            self.assertEqual((resumed / "37_run_0.json").read_bytes(), (output / "37_run_0.json").read_bytes())
            resumed_report = retry.read_json(resumed / "retry_manifest.json")
            self.assertEqual(resumed_report["request_count"], 3)
            self.assertEqual(resumed_report["reused_count"], 1)
            self.assertEqual(resumed_report["after"]["error_count"], 0)
            self.assertEqual(hashes, {path.name: retry.digest(path) for path in source.glob("*.json")})


if __name__ == "__main__":
    unittest.main()
