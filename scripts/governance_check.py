#!/usr/bin/env python3
"""Continuously prove the SentinelSRE agent governance invariants."""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.governance import ActionRequest, AuditLog, GovernancePolicy, IdentityRegistry, create_approval, verify_approval


def expect_denied(callback, expected: str) -> None:
    try:
        callback()
    except ValueError as exc:
        if expected not in str(exc):
            raise ValueError(f"expected denial containing '{expected}', got: {exc}") from exc
        return
    raise ValueError(f"unsafe operation was allowed; expected denial containing '{expected}'")


def main() -> int:
    policy = GovernancePolicy.load(ROOT / "agents/policy/governance.json")
    identities = IdentityRegistry.load(ROOT / "agents/identities/demo-identities.json")
    request = ActionRequest.from_dict({
        "api_version": "sentinelsre.io/v1",
        "kind": "ActionRequest",
        "incident_id": "INC-CONTINUOUS-CHECK",
        "requester": "IncidentInvestigatorAgent",
        "environment": "local",
        "action": "fault.recover",
        "target": "checkout-api",
        "parameters": {"base_url": "http://127.0.0.1:8080"},
        "risk": "medium",
        "evidence": ["controlled fault metric is active"],
        "verification": ["controlled fault metric returns to none"],
        "rollback": "Never restore an injected fault as rollback.",
        "created_at": "2026-08-14T12:00:00Z",
    })
    policy.validate(request, apply=True)

    now = dt.datetime(2026, 8, 14, 12, 1, tzinfo=dt.timezone.utc)
    secret = "continuous-governance-proof-key-2026"
    approval = create_approval(request, "sai.demo", secret, now=now)
    verify_approval(request, approval, secret, now=now)
    identities.require_approver("sai.demo", policy, "local")
    expect_denied(lambda: identities.require_approver("alex.observer", policy, "local"), "lacks an authorized role")
    expect_denied(lambda: create_approval(request, request.requester, secret, now=now), "distinct")
    expect_denied(
        lambda: policy.validate(ActionRequest.from_dict({**request.to_dict(), "action": "shell.execute"}), apply=True),
        "not allowlisted",
    )

    with tempfile.TemporaryDirectory(prefix="sentinelsre-audit-") as directory:
        audit = AuditLog(Path(directory) / "actions.jsonl")
        audit.append({"request_id": request.request_id, "outcome": "governance-check"})
        audit.verify()

    print("PASS allowlisted action validation")
    print("PASS signed approval binding and separation of duties")
    print("PASS identity role and active-status enforcement")
    print("PASS arbitrary action denial")
    print("PASS tamper-evident audit chain")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"FAIL governance: {exc}", file=sys.stderr)
        raise SystemExit(1)
