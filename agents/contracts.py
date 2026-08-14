"""Shared contracts that keep engineering agents reviewable and auditable."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    name: str
    passed: bool
    details: str


@dataclass
class AgentResult:
    agent: str
    objective: str
    mode: str
    risk: str
    approval_required: bool
    evidence: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    validations: list[ValidationResult] = field(default_factory=list)
    changes_applied: bool = False

    @property
    def successful(self) -> bool:
        return bool(self.validations) and all(item.passed for item in self.validations)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["successful"] = self.successful
        return payload
