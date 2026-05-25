import re
import time
import concurrent.futures
from typing import List, Dict, Any
from ..tools.python_tool import PythonTool
from ..utils.api_client import APIClient
from ..prompts.english_prompts import (
    SYSTEM_PROMPT_ENGLISH_COT as SYSTEM_PROMPT,
    FEW_SHOT_EXAMPLES,
    RESUME_TRIGGER
)

class ToolSolver:
    def __init__(self, model_config: Dict[str, Any]):
        self.model_config = model_config
        self.client = APIClient(
            base_url=model_config.get('base_url'), 
            api_key=model_config.get('api_key'),
            model=model_config.get('model'),
            api_type=model_config.get('api_type', 'openai'),
            default_headers=model_config.get('default_headers')
        )
        self.python_tool = PythonTool()
        self.max_turns = model_config.get('max_turns', 10)
        self.stop = model_config.get('stop', ["[/PYTHON]", "Observation:"])
        
        # If using a local model (e.g., LM Studio at localhost), allow skipping the system prompt
        base_url = (model_config.get('base_url') or "").lower()
        self.skip_system_prompt = model_config.get('skip_system_prompt', False) or ("localhost" in base_url)

        self.system_prompt = SYSTEM_PROMPT + "\n" + self.python_tool.get_prompt_description()
        self.few_shot_examples = FEW_SHOT_EXAMPLES
        self.use_few_shot = model_config.get("use_few_shot", False)
        self.require_python_tool = model_config.get("require_python_tool", False)
        self.temperature = model_config.get("temperature", 0.7)

        self.top_p = model_config.get("top_p", 1.0)
        self.frequency_penalty = model_config.get("frequency_penalty", 0.0)
        self.presence_penalty = model_config.get("presence_penalty", 0.0)
        self.reasoning_effort = model_config.get("reasoning_effort", None)
        self.python_timeout = model_config.get("python_timeout", 30)  # seconds
        # Some providers (e.g., Friendli serverless) reject overriding sampling params; allow opting out.
        self.sampling_params_locked = model_config.get("sampling_params_locked", False)

    def solve(self, problem: str) -> Dict[str, Any]:
        used_tool = False
        messages = []
        last_tool_error = False
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        start_time = time.time()
        if not self.skip_system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        if self.use_few_shot and self.few_shot_examples:
            for example in self.few_shot_examples:
                messages.append({"role": "user", "content": example["question"]})
                messages.append({"role": "assistant", "content": example["response"]})
        messages.append({
            "role": "user",
            "content": (
                problem
                + "\n\nReason step by step. Use the Python tool for calculations, verification, or long arithmetic; "
                "prefer it whenever it helps. Respond in one message with [THOUGHT] followed by the final answer in "
                "\\boxed{} and no code."
            )
        })
        
        history = []
        final_answer = None
        last_observation = None
        successful_tool_output = False
        
        for turn in range(self.max_turns):
            # Call model with retry logic
            response_text = ""
            for attempt in range(3):
                try:
                    call_kwargs = dict(messages=messages, reasoning_effort=self.reasoning_effort)
                    if not self.sampling_params_locked:
                        call_kwargs.update(
                            dict(
                                temperature=self.temperature,
                                top_p=self.top_p,
                                frequency_penalty=self.frequency_penalty,
                                presence_penalty=self.presence_penalty,
                            )
                        )
                    if self.client.api_type != "clova":
                        call_kwargs["stop"] = self.stop
                    response_text, usage = self.client.chat_completion(**call_kwargs)
                    if usage:
                        for key in token_usage:
                            if usage.get(key) is not None:
                                token_usage[key] += usage.get(key, 0)
                    if response_text and response_text.strip():
                        break
                    print(f"Attempt {attempt+1} failed: Empty response. Retrying...")
                except Exception as e:
                    print(f"Attempt {attempt+1} failed: {e}. Retrying...")
            
            if not response_text or not response_text.strip():
                print("Max retries reached. Moving to next problem.")
                break

            # Loop Detection
            if history and history[-1]["role"] == "assistant" and history[-1]["content"].strip() == response_text.strip():
                print("Loop detected! Forcing resume with specific instruction.")
                messages.append({"role": "user", "content": "You just generated that. Please proceed with the *result* of the code or move to the final answer."})
                continue
            
            history.append({"role": "assistant", "content": response_text})
            messages.append({"role": "assistant", "content": response_text})
            
            # Check for tool calls
            code_blocks = self._extract_code_blocks(response_text)
            has_final_box = "\\boxed{" in response_text
            if code_blocks and has_final_box:
                # Ignore premature final answers in the same turn as code; force to wait for observation.
                has_final_box = False
                messages.append({
                    "role": "user",
                    "content": (
                        "You included a \\boxed{} answer in the same message as code. "
                        "Wait for the Python output first, then reply with [THOUGHT] only and put the final answer in \\boxed{} with no code."
                    )
                })
            if code_blocks:
                used_tool = True
                tool_outputs = []
                last_tool_error = False
                successful_tool_output = False
                for code in code_blocks:
                    # Run python with timeout to prevent hangs
                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(self.python_tool.run, code)
                            output = future.result(timeout=self.python_timeout)
                    except concurrent.futures.TimeoutError:
                        output = f"Timeout: Python execution exceeded {self.python_timeout} seconds"
                        last_tool_error = True
                    except Exception as e:
                        output = f"{type(e).__name__}: {e}"
                        last_tool_error = True
                    # Drop stray "None" lines that confuse the model
                    cleaned_lines = []
                    for line in output.splitlines():
                        if line.strip() == "None":
                            continue
                        cleaned_lines.append(line)
                    output = "\n".join(cleaned_lines).strip()
                    if not output:
                        output = "No output"
                        last_tool_error = True
                    tool_outputs.append(f"[PYTHON OUTPUT]\n{output}\n[/PYTHON OUTPUT]")
                    lower_out = output.lower()
                    if (
                        "error" in output
                        or "traceback" in lower_out
                        or "no output" in lower_out
                        or "syntaxerror" in lower_out
                        or "timeout" in lower_out
                        or lower_out.strip() == "none"
                        or lower_out.startswith("none\n")
                    ):
                        last_tool_error = True
                
                tool_response = "\n".join(tool_outputs)
                last_observation = tool_response
                history.append({"role": "tool", "content": tool_response})
                # Give a crisp instruction to ground the final answer on the tool output.
                if last_tool_error:
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Observation:\n{tool_response}\n\n"
                            f"{RESUME_TRIGGER} Keep using [THOUGHT]/[PYTHON] and stop after each code block. "
                            "Use the values above as ground truth if available. Fix and rerun if needed, or continue reasoning. "
                            "When ready, reply with [THOUGHT] only and give the final answer in \\boxed{} with no code."
                        )
                    })
                else:
                    successful_tool_output = True
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Observation:\n{tool_response}\n\n"
                            "Valid Python output. If you need another short computation, you may run more [PYTHON]. "
                            "Otherwise reply with [THOUGHT] and give the final answer in \\boxed{} using this output as ground truth. No code."
                        )
                    })
            else:
                # No tool call. If we already have a valid observation and asked for final, just prompt for boxed answer.
                if successful_tool_output:
                    messages.append({
                        "role": "user",
                        "content": (
                            "Provide your final answer now with [THOUGHT] and put the final answer in \\boxed{}, using the last Observation as ground truth. No code."
                        )
                    })
                else:
                    # No tool call and no final answer yet: either use Python or conclude now.
                    messages.append({
                        "role": "user",
                        "content": (
                            "Use Python to verify or compute unless the answer is immediate. "
                            "If you choose to verify, wrap code in [THOUGHT]/[PYTHON] and stop after the code so it can run. "
                            "Otherwise, respond with [THOUGHT] and the final answer in \\boxed{} with no code."
                        )
                    })

            # Check for final answer (only allow after at least one tool use)
            if has_final_box:
                final_answer = self._extract_boxed(response_text)
                break
        
        # Last Chance Mechanism
        if final_answer is None:
            print("Max turns reached without final answer. Attempting last chance...")
            messages.append({
                "role": "user",
                "content": (
                    "Please provide your final answer now with the value inside \\boxed{}."
                )
            })
            
            try:
                call_kwargs = dict(
                    messages=messages,
                    temperature=self.temperature,
                )
                if self.client.api_type != "clova":
                    call_kwargs["stop"] = self.stop
                response_text, usage = self.client.chat_completion(**call_kwargs)
                if usage:
                    for key in token_usage:
                        if usage.get(key) is not None:
                            token_usage[key] += usage.get(key, 0)
                history.append({"role": "assistant", "content": response_text})
                if "\\boxed{" in response_text:
                    final_answer = self._extract_boxed(response_text)
            except Exception as e:
                print(f"Last chance failed: {e}")

        elapsed_time = time.time() - start_time

        return {
            "problem": problem,
            "final_answer": final_answer,
            "history": history,
            "solved": final_answer is not None,
            "token_usage": token_usage,
            "elapsed_time_sec": elapsed_time
        }

    def _extract_code_blocks(self, text: str) -> List[str]:
        # 1. Try to find [PYTHON]...[/PYTHON] tags first (Explicit instruction)
        pattern_tags = r"\[PYTHON\](.*?)\[/PYTHON\]"
        matches = re.findall(pattern_tags, text, re.DOTALL)
        if matches:
            return [m.strip() for m in matches if m.strip()]

        # Handle dangling [PYTHON] without closing tag by taking until the end
        # Also handle cases where [PYTHON] is used as a closing tag (common error)
        if "[PYTHON]" in text:
            fragments = text.split("[PYTHON]")
            # We might have multiple [PYTHON] tags. Let's look at the last one or iterate.
            # Usually the model outputs text then [PYTHON] code...
            # If it uses [PYTHON] to close, it might look like: [PYTHON] code [PYTHON]
            
            # Let's try to find the content between the last [PYTHON] and the end or next [PYTHON]
            if len(fragments) > 1:
                last_fragment = fragments[-1]
                # If there was a [PYTHON] before this, the content is in the fragment before the last one if the last one is empty/short?
                # Actually, if we split by [PYTHON], and we have "text [PYTHON] code [PYTHON]", we get ["text ", " code ", ""]
                
                # Let's try to parse from the first [PYTHON] found
                candidate = text.split("[PYTHON]", 1)[1]
                
                # Check if it's closed by [/PYTHON] (already handled by regex above, but maybe malformed?)
                if "[/PYTHON]" in candidate:
                    candidate = candidate.split("[/PYTHON]", 1)[0]
                
                # Check if it's closed by another [PYTHON] (common error)
                elif "[PYTHON]" in candidate:
                     candidate = candidate.split("[PYTHON]", 1)[0]
                
                candidate = candidate.strip()
                if "```" in candidate:
                    candidate = candidate.split("```", 1)[0]
                
                if candidate:
                    return [candidate]

        # 2. Try to find markdown code blocks (Explicit instruction alternative)
        # Allow for optional whitespace/newline after python
        pattern_markdown = r"```python\s*(.*?)```"
        matches = re.findall(pattern_markdown, text, re.DOTALL)
        if matches:
            return [m.strip() for m in matches if m.strip()]

        # 2b. Generic ```...``` blocks (no language hint)
        pattern_generic = r"```(?:[^\n]*)?\n(.*?)```"
        matches = re.findall(pattern_generic, text, re.DOTALL)
        if matches:
            return [m.strip() for m in matches if m.strip()]

        # 2c. Handle cases where the model forgets to close the triple backticks
        if "```" in text:
            start = text.rfind("```python")
            lang_len = len("```python")
            if start == -1:
                start = text.rfind("```")
                lang_len = len("```")
            if start != -1:
                fragment = text[start + lang_len :]
                if fragment.startswith("\n"):
                    fragment = fragment[1:]
                fragment = fragment.strip()
                if fragment:
                    return [fragment]

        # 3. Handle DeepSeek Chimera specific format
        # Pattern: <|start|>assistant<|channel|>commentary to=python code<|message|>...
        # We extract the content after <|message|>
        # Sometimes <|call|> is missing if the model stops early or just ends.
        if "<|message|>" in text:
            parts = text.split("<|message|>")
            if len(parts) > 1:
                code_part = parts[1]
                # If <|call|> exists, stop there
                if "<|call|>" in code_part:
                    code_part = code_part.split("<|call|>")[0]
                snippet = code_part.strip()
                if snippet:
                    return [snippet]
            
        return []

    def _extract_boxed(self, text: str) -> str:
        idx = text.rfind("\\boxed{")
        if idx == -1:
            return None
        
        # Move to the opening brace of \boxed{
        idx += 6
        if idx >= len(text) or text[idx] != "{":
            return None
            
        brace_count = 0
        content = ""
        
        for i in range(idx, len(text)):
            char = text[i]
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
            
            if brace_count == 0:
                return content[1:] # Remove leading {
            
            content += char
            
        return None
