from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from math_eval_v8.types import VerifierResult


_SORRY_RE = re.compile(r"(?<![A-Za-z_])(?:sorry|admit)(?![A-Za-z_])")
_DIAG_RE = re.compile(
    r"^(?P<path>[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<severity>error|warning|info):\s*(?P<body>.+)$",
    flags=re.MULTILINE,
)


def strip_lean_comments(code: str) -> str:
    without_line_comments = re.sub(r"--.*?$", "", code or "", flags=re.MULTILINE)
    return re.sub(r"/-.*?-/", "", without_line_comments, flags=re.DOTALL)


def contains_sorry_or_admit(code: str) -> bool:
    return bool(_SORRY_RE.search(strip_lean_comments(code)))


def extract_lean_block(text: str) -> str:
    matches = list(re.finditer(r"```lean4?\s*\n(.*?)```", text or "", flags=re.DOTALL | re.IGNORECASE))
    if matches:
        return matches[-1].group(1).strip()
    return (text or "").strip()


def parse_diagnostics(stdout: str, stderr: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for match in _DIAG_RE.finditer(stdout + "\n" + stderr):
        line = f"{match.group('severity')}:{match.group('line')}:{match.group('col')}: {match.group('body').strip()}"
        if match.group("severity") == "error":
            errors.append(line)
        elif match.group("severity") == "warning":
            warnings.append(line)
    return errors, warnings


def ensure_imports(code: str, default_imports: list[str] | None) -> str:
    if re.search(r"^\s*import\s+\S+", code, flags=re.MULTILINE):
        return code.strip() + "\n"
    imports = "\n".join(["import Mathlib"] if default_imports is None else default_imports)
    if not imports.strip():
        return code.strip() + "\n"
    return f"{imports}\n\n{code.strip()}\n"


def verify_lean_code(
    code: str,
    *,
    lean_project_path: str | None = None,
    default_imports: list[str] | None = None,
    timeout_s: float = 60.0,
    lean_num_threads: int | None = None,
) -> VerifierResult:
    started = time.monotonic()
    prepared = ensure_imports(extract_lean_block(code), default_imports)
    source_hash = hashlib.sha256(prepared.encode("utf-8")).hexdigest()

    with tempfile.NamedTemporaryFile("w", suffix=".lean", encoding="utf-8", delete=False) as handle:
        handle.write(prepared)
        temp_path = handle.name

    try:
        env = os.environ.copy()
        if lean_num_threads:
            env["LEAN_NUM_THREADS"] = str(lean_num_threads)
        if lean_project_path:
            cmd = ["lake", "env", "lean", temp_path]
            cwd = str(Path(lean_project_path).expanduser().resolve())
        else:
            cmd = ["lean", temp_path]
            cwd = None
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            return VerifierResult(
                ok=False,
                complete=False,
                elapsed_sec=time.monotonic() - started,
                source_hash=source_hash,
                system_error=f"lean timed out after {timeout_s}s",
            )
        errors, warnings = parse_diagnostics(stdout, stderr)
        if proc.returncode != 0 and not errors:
            raw = (stderr or stdout or "").strip()
            if raw:
                errors.append(raw[-2000:])
        sorries = contains_sorry_or_admit(prepared)
        failed_warning = any("declaration uses 'sorry'" in w or "failed" in w.lower() for w in warnings)
        ok = proc.returncode == 0 and not errors
        return VerifierResult(
            ok=ok,
            complete=ok and not sorries and not failed_warning,
            errors=errors,
            warnings=warnings,
            sorries=sorries,
            elapsed_sec=time.monotonic() - started,
            source_hash=source_hash,
        )
    except FileNotFoundError as exc:
        return VerifierResult(
            ok=False,
            complete=False,
            elapsed_sec=time.monotonic() - started,
            source_hash=source_hash,
            system_error=str(exc),
        )
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
