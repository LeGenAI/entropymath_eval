from __future__ import annotations

import os
import time
from typing import Any

from openai import OpenAI


class APIClient:
    def __init__(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        model: str,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.model = model
        self.client = OpenAI(
            base_url=base_url or os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1"),
            api_key=api_key or os.getenv("OPENAI_API_KEY", "not-needed"),
            default_headers=default_headers or {},
        )

    def chat_completion(self, messages: list[dict[str, str]], **kwargs: Any) -> tuple[str, dict[str, int | None] | None]:
        kwargs.setdefault("timeout", 600)
        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    **kwargs,
                )
                content = response.choices[0].message.content or ""
                usage = None
                if getattr(response, "usage", None):
                    usage = {
                        "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                        "completion_tokens": getattr(response.usage, "completion_tokens", None),
                        "total_tokens": getattr(response.usage, "total_tokens", None),
                    }
                return content, usage
            except Exception as exc:
                if attempt == 2:
                    raise RuntimeError(f"model request failed after retries: {exc}") from exc
                time.sleep(1)
        return "", None

    def completion(self, prompt: str, **kwargs: Any) -> tuple[str, dict[str, int | None] | None]:
        kwargs.setdefault("timeout", 600)
        for attempt in range(3):
            try:
                response = self.client.completions.create(
                    model=self.model,
                    prompt=prompt,
                    **kwargs,
                )
                content = response.choices[0].text or ""
                usage = None
                if getattr(response, "usage", None):
                    usage = {
                        "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                        "completion_tokens": getattr(response.usage, "completion_tokens", None),
                        "total_tokens": getattr(response.usage, "total_tokens", None),
                    }
                return content, usage
            except Exception as exc:
                if attempt == 2:
                    raise RuntimeError(f"completion request failed after retries: {exc}") from exc
                time.sleep(1)
        return "", None
