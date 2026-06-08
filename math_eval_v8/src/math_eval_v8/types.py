from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class BenchmarkRow:
    problem_id: str
    formal_statement: str
    informal_statement: str | None = None
    header: str | None = None
    split: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VerifierResult:
    ok: bool
    complete: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sorries: bool = False
    elapsed_sec: float = 0.0
    source_hash: str | None = None
    system_error: str | None = None

    def summary(self) -> str:
        if self.system_error:
            return f"system error: {self.system_error}"
        if self.complete:
            return "complete"
        return "\n".join((self.errors or self.warnings)[:5]) or "incomplete"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)
