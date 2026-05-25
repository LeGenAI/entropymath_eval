from __future__ import annotations

import re
import time
from typing import Any, Dict

from ..utils.api_client import APIClient


SYSTEM_PROMPT = (
    "You are solving a mathematical evaluation problem. Reason carefully and "
    "self-check your work, but do not use external tools. Put only the final "
    "answer inside \\boxed{}."
)

USER_PROMPT_TEMPLATE = (
    "{problem}\n\n"
    "Reason step by step. Do not call tools or write executable code. Put the "
    "final answer in \\boxed{{}}."
)


class DirectSolver:
    """Single-call no-tool solver for paper-facing benchmark comparability."""

    def __init__(self, model_config: Dict[str, Any]):
        self.model_config = model_config
        self.client = APIClient(
            base_url=model_config.get("base_url"),
            api_key=model_config.get("api_key"),
            model=model_config.get("model"),
            api_type=model_config.get("api_type", "openai"),
            default_headers=model_config.get("default_headers"),
        )
        base_url = (model_config.get("base_url") or "").lower()
        self.skip_system_prompt = model_config.get("skip_system_prompt", False) or (
            "localhost" in base_url
        )
        self.temperature = model_config.get("temperature", 0.0)
        self.top_p = model_config.get("top_p", 1.0)
        self.frequency_penalty = model_config.get("frequency_penalty", 0.0)
        self.presence_penalty = model_config.get("presence_penalty", 0.0)
        self.reasoning_effort = model_config.get("reasoning_effort") or model_config.get(
            "effort"
        )
        self.sampling_params_locked = model_config.get("sampling_params_locked", False)
        self.max_tokens = model_config.get("max_tokens")
        self.request_timeout = model_config.get("request_timeout")
        self.prompt_template = SYSTEM_PROMPT + "\n\n" + USER_PROMPT_TEMPLATE

    def solve(self, problem: str) -> Dict[str, Any]:
        messages = []
        if not self.skip_system_prompt:
            messages.append({"role": "system", "content": SYSTEM_PROMPT})
        messages.append(
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(problem=problem)}
        )

        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        start_time = time.time()
        response_text = ""
        usage = None

        call_kwargs = dict(messages=messages)
        if self.reasoning_effort:
            call_kwargs["reasoning_effort"] = self.reasoning_effort
        if not self.sampling_params_locked:
            call_kwargs.update(
                dict(
                    temperature=self.temperature,
                    top_p=self.top_p,
                    frequency_penalty=self.frequency_penalty,
                    presence_penalty=self.presence_penalty,
                )
            )
        if isinstance(self.max_tokens, int) and self.max_tokens > 0:
            call_kwargs["max_tokens"] = self.max_tokens
        if self.request_timeout is not None:
            call_kwargs["timeout"] = self.request_timeout

        response_text, usage = self.client.chat_completion(**call_kwargs)
        if not response_text or not response_text.strip():
            raise RuntimeError("Empty model response; check provider authentication, model id, or request parameters.")
        if usage:
            for key in token_usage:
                if usage.get(key) is not None:
                    token_usage[key] += usage.get(key, 0)

        final_answer = self._extract_boxed(response_text)
        elapsed_time = time.time() - start_time
        return {
            "problem": problem,
            "final_answer": final_answer,
            "history": [{"role": "assistant", "content": response_text}],
            "solved": final_answer is not None,
            "token_usage": token_usage,
            "elapsed_time_sec": elapsed_time,
            "solver_protocol": "direct_no_tool",
            "answer_extraction_status": "boxed_found" if final_answer else "missing_boxed",
        }

    def _extract_boxed(self, text: str) -> str | None:
        if not text:
            return None
        idx = text.rfind("\\boxed{")
        if idx == -1:
            return None

        idx += len("\\boxed")
        if idx >= len(text) or text[idx] != "{":
            return None

        brace_count = 0
        content = ""
        for char in text[idx:]:
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1

            if brace_count == 0:
                return content[1:].strip()
            content += char

        fallback = re.search(r"\\boxed\{([^{}]+)\}", text)
        return fallback.group(1).strip() if fallback else None
