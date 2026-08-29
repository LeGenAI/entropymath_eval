import os
import requests
import json
import uuid
from openai import APITimeoutError, OpenAI, RateLimitError
from typing import List, Dict, Any

class ClovaStudioClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clova v3 expects content as an array of {type: text, text: ...}."""
        converted = []
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            converted.append({"role": m.get("role", "user"), "content": content})
        return converted

    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> tuple:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
            "Content-Type": "application/json",
            "Accept": "text/event-stream"
        }
        
        data = {
            "messages": self._convert_messages(messages),
            "topP": kwargs.get("top_p", 0.8),
            "topK": kwargs.get("top_k", 0),
            "maxCompletionTokens": kwargs.get("max_tokens", 20480),
            "temperature": kwargs.get("temperature", 0.5),
            # Clova docs use both repetitionPenalty / repeatPenalty in examples; send both to be safe.
            "repetitionPenalty": kwargs.get("repetition_penalty", 1.1),
            "repeatPenalty": kwargs.get("repetition_penalty", 1.1),
            "thinking": kwargs.get("thinking", {"effort": "low"}),
            "includeAiFilters": kwargs.get("include_ai_filters", True)
        }
        
        # Handle tools if present (not implemented in this basic version yet, but structure is there)
        
        try:
            print(f"DEBUG: Clova Request to {self.base_url}")
            # Streaming request
            response = requests.post(self.base_url, headers=headers, json=data, stream=True)
            status_code = response.status_code
            try:
                response.raise_for_status()
            except APITimeoutError as e:
                print(f"API request timed out; skipping this run: {e}")
                return "", None
            except Exception as e:
                # Log status and a snippet of the body for debugging
                try:
                    print(f"Clova HTTP Error {status_code}: {response.text[:500]}")
                except Exception:
                    pass
                raise
            
            debug_lines = []
            # Handle event stream
            content_parts = []
            usage = None
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    debug_lines.append(decoded_line)
                    if decoded_line.startswith("data:"):
                        json_str = decoded_line[5:].strip()
                        if json_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(json_str)
                            if "usage" in chunk and chunk["usage"]:
                                usage = chunk["usage"]
                            if "message" in chunk and "content" in chunk["message"]:
                                # Streaming token event
                                content_parts.append(chunk["message"].get("content", "") or "")
                            elif "result" in chunk:
                                # Final response format
                                content_parts.append(chunk["result"]["message"].get("content", "") or "")
                                if "usage" in chunk.get("result", {}) and chunk["result"]["usage"]:
                                    usage = chunk["result"]["usage"]
                        except json.JSONDecodeError:
                            pass
            
            # If streaming wasn't handled correctly or it was a single response
            if not content_parts:
                # Try non-streaming fallback
                try:
                    fallback_headers = headers.copy()
                    fallback_headers["Accept"] = "application/json"
                    resp2 = requests.post(self.base_url, headers=fallback_headers, json=data, stream=False)
                    status2 = resp2.status_code
                    resp2.raise_for_status()
                    as_json = resp2.json()
                    result = as_json.get("result", {})
                    msg = result.get("message", {})
                    if msg.get("content"):
                        content_parts.append(msg.get("content", ""))
                    if result.get("usage"):
                        usage = result.get("usage")
                except Exception as e:
                    try:
                        print(f"DEBUG: Clova fallback parse failed: {e}, status={status_code}, body={response.text[:500]}, debug_lines={debug_lines[:5]}")
                    except Exception:
                        pass

            full_content = "".join(content_parts)

            # Normalize usage keys to match OpenAI-style when possible
            if usage:
                usage = {
                    "prompt_tokens": usage.get("promptTokens"),
                    "completion_tokens": usage.get("completionTokens"),
                    "total_tokens": usage.get("totalTokens"),
                }

            return full_content, usage
            
        except Exception as e:
            print(f"Clova API Error: {e}")
            return "", None

class APIClient:
    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        model: str = "gpt-oss-20b",
        api_type: str = "openai",
        default_headers: Dict[str, str] = None,
    ):
        self.api_type = api_type
        self.model = model
        
        if api_type == "clova":
            self.client = ClovaStudioClient(base_url, api_key)
        else:
            self.client = OpenAI(
                base_url=base_url or os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1"),
                api_key=api_key or os.getenv("OPENAI_API_KEY", "not-needed"),
                default_headers=default_headers or {},
                max_retries=0,
            )

    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> tuple:
        if self.api_type == "clova":
            return self.client.chat_completion(messages, **kwargs)
            
        max_retries = 10
        # Prevent indefinite blocking if the local server stops responding.
        kwargs.setdefault("timeout", 600)
        debug_api = os.getenv("MATH_EVAL_DEBUG_API") == "1"
        for attempt in range(max_retries):
            try:
                if debug_api:
                    print(f"DEBUG: Sending messages: {messages}")
                    print(f"DEBUG: Requesting model: {self.model}")
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    **kwargs
                )
                content = response.choices[0].message.content
                usage = None
                if hasattr(response, "usage") and response.usage:
                    # response.usage may have prompt_tokens, completion_tokens, total_tokens
                    usage = {
                        "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                        "completion_tokens": getattr(response.usage, "completion_tokens", None),
                        "total_tokens": getattr(response.usage, "total_tokens", None),
                    }
                if debug_api:
                    print(f"DEBUG: Received content: {content!r}")
                
                if not content:
                    print("Warning: Empty content received; skipping this run.")
                        
                return content, usage
            except APITimeoutError as e:
                print(f"API request timed out; skipping this run: {e}")
                return "", None
            except RateLimitError:
                print(f"API rate limit reached (attempt {attempt + 1}/{max_retries}); waiting 60 seconds.")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(60)
                else:
                    return "", None
            except Exception as e:
                print(f"API Error (Attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)  # Simple backoff
                else:
                    return "", None
        return "", None
