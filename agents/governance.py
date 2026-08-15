"""Policy, approval, and tamper-evident audit primitives for SRE agents."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def parse_time(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


@dataclass(frozen=True)
class ActionRequest:
    api_version: str
    kind: str
    incident_id: str
    requester: str
    environment: str
    action: str
    target: str
    parameters: dict[str, Any]
    risk: str
    evidence: list[str]
    verification: list[str]
    rollback: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def digest(self) -> str:
        return sha256(self.to_dict())

    @property
    def request_id(self) -> str:
        return f"ACT-{self.digest[:12].upper()}"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ActionRequest":
        expected = {field.name for field in cls.__dataclass_fields__.values()}
        if set(value) != expected:
            raise ValueError(f"action request fields must be exactly: {', '.join(sorted(expected))}")
        request = cls(**value)
        if request.api_version != "sentinelsre.io/v1" or request.kind != "ActionRequest":
            raise ValueError("unsupported action request contract")
        if request.risk not in {"low", "medium", "high", "critical"}:
            raise ValueError("invalid risk classification")
        if not request.evidence or not request.verification or not request.rollback.strip():
            raise ValueError("evidence, verification, and rollback are mandatory")
        parse_time(request.created_at)
        return request


@dataclass(frozen=True)
class Approval:
    api_version: str
    kind: str
    request_id: str
    request_digest: str
    approver: str
    decision: str
    issued_at: str
    expires_at: str
    signature: str

    def unsigned(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("signature")
        return value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Approval":
        return cls(**value)


class GovernancePolicy:
    def __init__(self, value: dict[str, Any]):
        self.value = value

    @classmethod
    def load(cls, path: Path) -> "GovernancePolicy":
        return cls(json.loads(path.read_text()))

    def validate(self, request: ActionRequest, apply: bool) -> dict[str, Any]:
        environments = self.value.get("environments", {})
        if request.environment not in environments:
            raise ValueError(f"environment '{request.environment}' is not governed")
        environment = environments[request.environment]
        action = self.value.get("actions", {}).get(request.action)
        if not action:
            raise ValueError(f"action '{request.action}' is not allowlisted")
        if request.requester not in action.get("requesters", []):
            raise ValueError(f"requester '{request.requester}' cannot propose '{request.action}'")
        if request.risk != action.get("risk"):
            raise ValueError(f"risk for '{request.action}' must be classified as {action.get('risk')}")
        if request.environment not in action.get("environments", []):
            raise ValueError(f"action '{request.action}' is prohibited in {request.environment}")
        if not re.fullmatch(action["target_pattern"], request.target):
            raise ValueError(f"target '{request.target}' is outside the policy scope")
        if apply and environment.get("draft_only", True):
            raise ValueError(f"{request.environment} is draft-only; execution is prohibited")
        if apply and not action.get("executable", False):
            raise ValueError(f"action '{request.action}' cannot be executed")

        allowed_parameters = set(action.get("parameters", {}))
        unknown = set(request.parameters) - allowed_parameters
        if unknown:
            raise ValueError(f"parameters are not allowlisted: {', '.join(sorted(unknown))}")
        for name, constraint in action.get("parameters", {}).items():
            if name not in request.parameters:
                if constraint.get("required", False):
                    raise ValueError(f"parameter '{name}' is required")
                continue
            value = request.parameters[name]
            if "enum" in constraint and value not in constraint["enum"]:
                raise ValueError(f"parameter '{name}' is outside its allowlist")
            if "minimum" in constraint and value < constraint["minimum"]:
                raise ValueError(f"parameter '{name}' is below its minimum")
            if "maximum" in constraint and value > constraint["maximum"]:
                raise ValueError(f"parameter '{name}' exceeds its maximum")
        return action

    def approver_roles(self, environment: str) -> set[str]:
        try:
            return set(self.value["environments"][environment]["approver_roles"])
        except KeyError as exc:
            raise ValueError(f"no approver roles configured for '{environment}'") from exc


class IdentityRegistry:
    def __init__(self, value: dict[str, Any]):
        self.value = value

    @classmethod
    def load(cls, path: Path) -> "IdentityRegistry":
        return cls(json.loads(path.read_text()))

    def require_approver(self, identity: str, policy: GovernancePolicy, environment: str) -> None:
        record = self.value.get("identities", {}).get(identity)
        if not record:
            raise ValueError(f"approver '{identity}' is not in the identity registry")
        if not record.get("active", False):
            raise ValueError(f"approver '{identity}' is inactive")
        if not set(record.get("roles", [])) & policy.approver_roles(environment):
            raise ValueError(f"approver '{identity}' lacks an authorized role for {environment}")


def create_approval(
    request: ActionRequest,
    approver: str,
    secret: str,
    now: dt.datetime | None = None,
    ttl_minutes: int = 15,
) -> Approval:
    if len(secret) < 32:
        raise ValueError("approval secret must contain at least 32 characters")
    if not 1 <= ttl_minutes <= 60:
        raise ValueError("approval TTL must be between 1 and 60 minutes")
    if not approver.strip() or approver == request.requester:
        raise ValueError("approver must be a distinct, non-empty human identity")
    issued = (now or utc_now()).astimezone(dt.timezone.utc).replace(microsecond=0)
    unsigned = {
        "api_version": "sentinelsre.io/v1",
        "kind": "Approval",
        "request_id": request.request_id,
        "request_digest": request.digest,
        "approver": approver,
        "decision": "approved",
        "issued_at": issued.isoformat().replace("+00:00", "Z"),
        "expires_at": (issued + dt.timedelta(minutes=ttl_minutes)).isoformat().replace("+00:00", "Z"),
    }
    signature = hmac.new(secret.encode(), canonical(unsigned).encode(), hashlib.sha256).hexdigest()
    return Approval(**unsigned, signature=signature)


def verify_approval(
    request: ActionRequest,
    approval: Approval,
    secret: str,
    now: dt.datetime | None = None,
) -> None:
    if approval.api_version != "sentinelsre.io/v1" or approval.kind != "Approval":
        raise ValueError("unsupported approval contract")
    if approval.decision != "approved":
        raise ValueError("request is not approved")
    if approval.request_id != request.request_id or approval.request_digest != request.digest:
        raise ValueError("approval is not bound to this exact request")
    if approval.approver == request.requester:
        raise ValueError("requester cannot approve their own action")
    expected = hmac.new(secret.encode(), canonical(approval.unsigned()).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, approval.signature):
        raise ValueError("approval signature is invalid")
    effective_now = (now or utc_now()).astimezone(dt.timezone.utc)
    if effective_now > parse_time(approval.expires_at):
        raise ValueError("approval has expired")
    if effective_now < parse_time(approval.issued_at) - dt.timedelta(seconds=30):
        raise ValueError("approval was issued in the future")


class AuditLog:
    """Append-only hash chain. External immutable storage remains a production concern."""

    def __init__(self, path: Path):
        self.path = path

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def verify(self) -> None:
        previous = "GENESIS"
        for index, record in enumerate(self.records(), start=1):
            actual_hash = record.get("event_hash")
            unsigned = dict(record)
            unsigned.pop("event_hash", None)
            if unsigned.get("previous_hash") != previous or sha256(unsigned) != actual_hash:
                raise ValueError(f"audit chain is invalid at record {index}")
            previous = actual_hash

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        self.verify()
        records = self.records()
        previous = records[-1]["event_hash"] if records else "GENESIS"
        record = {**event, "previous_hash": previous}
        record["event_hash"] = sha256(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(canonical(record) + "\n")
            handle.flush()
        return record
