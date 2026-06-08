from __future__ import annotations

import re
import time
from typing import Any

from math_eval_v8.types import BenchmarkRow
from math_eval_v8.utils.api_client import APIClient
from math_eval_v8.verifiers.lean_verifier import extract_lean_block


SYSTEM_PROMPT = (
    "You are a Lean 4 theorem prover. Return a complete Lean 4 proof. "
    "Do not use sorry, admit, or placeholders."
)
BFS_SEPARATOR = ":::"


def _has_proof_body(statement: str) -> bool:
    return bool(re.search(r":=\s*by\b", statement or ""))


def _remove_placeholder_proof(statement: str) -> str:
    text = statement.strip()
    text = re.sub(r":=\s*by\s*(?:sorry|admit)\s*$", ":= by", text)
    text = re.sub(r":=\s*(?:sorry|admit)\s*$", ":= by", text)
    return text


class LeanSolver:
    def __init__(self, model_config: dict[str, Any], benchmark_config: dict[str, Any]) -> None:
        self.model_config = model_config
        self.benchmark_config = benchmark_config
        self.client = APIClient(
            base_url=model_config.get("base_url"),
            api_key=model_config.get("api_key"),
            model=model_config.get("model"),
            default_headers=model_config.get("default_headers"),
        )
        self.temperature = model_config.get("temperature", 0.2)
        self.top_p = model_config.get("top_p", 1.0)
        self.max_tokens = model_config.get("max_tokens", 4096)
        self.skip_system_prompt = model_config.get("skip_system_prompt", False)
        self.request_timeout = model_config.get("request_timeout", 600)
        self.default_imports = benchmark_config.get("default_imports") or ["import Mathlib"]
        self.prompt_style = model_config.get("prompt_style", "whole_proof")

    def build_prompt(self, row: BenchmarkRow, repair: str | None = None) -> str:
        use_row_header = self.benchmark_config.get("use_row_header", True)
        imports = (row.header if use_row_header and row.header else "\n".join(self.default_imports)).strip()
        statement = _remove_placeholder_proof(row.formal_statement)
        if not _has_proof_body(statement):
            statement = statement.rstrip()
            if statement.endswith(":="):
                statement += " by"
            else:
                statement += " := by"
        natural = f"\n\nInformal statement:\n{row.informal_statement.strip()}" if row.informal_statement else ""
        repair_block = f"\n\nPrevious Lean feedback:\n{repair}" if repair else ""
        return (
            "Produce exactly one fenced ```lean4 block and no prose outside it.\n"
            "The file must compile in Lean 4. Do not use sorry or admit.\n\n"
            "Use these imports unless the benchmark row already requires a more specific import:\n"
            f"```lean4\n{imports}\n```\n"
            f"{natural}\n\n"
            "Complete this theorem:\n"
            f"```lean4\n{statement}\n```\n"
            f"{repair_block}"
        )

    def build_bfs_prompt(self, row: BenchmarkRow) -> tuple[str, str]:
        prefix = _remove_placeholder_proof(row.formal_statement)
        if not _has_proof_body(prefix):
            prefix = prefix.rstrip()
            prefix = prefix + (" by" if prefix.endswith(":=") else " := by")
        use_row_header = self.benchmark_config.get("use_row_header", True)
        imports = (row.header if use_row_header and row.header else "\n".join(self.default_imports)).strip()
        formal_prefix = f"{imports}\n\n{prefix}".rstrip()
        return f"{formal_prefix}{BFS_SEPARATOR}", formal_prefix

    @staticmethod
    def _clean_bfs_tactic(text: str) -> str:
        tactic = (text or "").strip()
        if tactic.startswith("|>"):
            tactic = tactic[2:].strip()
        if tactic.startswith(BFS_SEPARATOR):
            tactic = tactic[len(BFS_SEPARATOR):].strip()
        return tactic.split(BFS_SEPARATOR, 1)[0].strip()

    def solve(self, row: BenchmarkRow, *, repair: str | None = None) -> dict[str, Any]:
        if self.prompt_style == "bfs_tactic":
            prompt, formal_prefix = self.build_bfs_prompt(row)
            started = time.time()
            kwargs: dict[str, Any] = {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "timeout": self.request_timeout,
                "stop": [BFS_SEPARATOR, "\n\n"],
            }
            if isinstance(self.max_tokens, int) and self.max_tokens > 0:
                kwargs["max_tokens"] = self.max_tokens
            response_text, usage = self.client.completion(prompt, **kwargs)
            tactic = self._clean_bfs_tactic(response_text)
            candidate_code = formal_prefix + ("\n  " + tactic if tactic else "\n")
            return {
                "prompt": prompt,
                "model_output": response_text,
                "candidate_code": candidate_code,
                "token_usage": usage,
                "elapsed_time_sec": time.time() - started,
                "solver_metadata": {"prompt_style": self.prompt_style, "tactic": tactic},
            }

        messages: list[dict[str, str]] = []
        if not self.skip_system_prompt:
            messages.append({"role": "system", "content": SYSTEM_PROMPT})
        prompt = self.build_prompt(row, repair=repair)
        messages.append({"role": "user", "content": prompt})

        started = time.time()
        kwargs: dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "timeout": self.request_timeout,
        }
        if isinstance(self.max_tokens, int) and self.max_tokens > 0:
            kwargs["max_tokens"] = self.max_tokens
        response_text, usage = self.client.chat_completion(messages, **kwargs)
        candidate_code = extract_lean_block(response_text)
        return {
            "prompt": prompt,
            "model_output": response_text,
            "candidate_code": candidate_code,
            "token_usage": usage,
            "elapsed_time_sec": time.time() - started,
        }
