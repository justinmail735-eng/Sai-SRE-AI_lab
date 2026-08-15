#!/usr/bin/env python3
"""Generate an evidence-linked blameless postmortem from agent and audit records."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.governance import ActionRequest, AuditLog


def escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def load_evidence(investigation_path: Path, audit_path: Path) -> tuple[dict[str, Any], ActionRequest, dict[str, Any]]:
    investigation = json.loads(investigation_path.read_text())
    if investigation.get("kind") != "IncidentInvestigation":
        raise ValueError("investigation has the wrong kind")
    recommended = investigation.get("recommended_action")
    if not recommended:
        raise ValueError("investigation contains no recommended action")
    request_value = dict(recommended)
    claimed_id = request_value.pop("request_id", None)
    request = ActionRequest.from_dict(request_value)
    if claimed_id != request.request_id:
        raise ValueError("investigation request identifier does not match its content")

    audit = AuditLog(audit_path)
    audit.verify()
    matching = [record for record in audit.records() if record.get("request_id") == request.request_id]
    if len(matching) != 1:
        raise ValueError(f"expected exactly one matching audit event, found {len(matching)}")
    event = matching[0]
    if event.get("request_digest") != request.digest:
        raise ValueError("audit event is not bound to the investigated request")
    return investigation, request, event


def build_postmortem(investigation: dict[str, Any], request: ActionRequest, audit: dict[str, Any]) -> dict[str, Any]:
    hypothesis = investigation["hypotheses"][0]
    checkout_evidence = next((item for item in request.evidence if "GET /checkout" in item), "synthetic checkout failed")
    status_match = re.search(r"HTTP (\d{3})", checkout_evidence)
    status = status_match.group(1) if status_match else "unknown"
    resolved = audit.get("outcome") == "succeeded" and bool(audit.get("verification"))
    return {
        "api_version": "sentinelsre.io/v1",
        "kind": "IncidentPostmortem",
        "incident_id": request.incident_id,
        "status": "resolved" if resolved else "unresolved",
        "severity": "SEV-2" if status.startswith("5") else "SEV-3",
        "summary": "Controlled checkout failure exercised SentinelSRE detection, governance, recovery, and verification.",
        "impact": f"Local synthetic checkout requests returned HTTP {status}. No production users or cloud resources were involved.",
        "detection": "Incident Investigator Agent correlated a failed checkout request with the exported fault-mode metric.",
        "root_cause": hypothesis["summary"],
        "contributing_factors": [
            "The basic health endpoint stayed green while the user-facing checkout path failed.",
            "The experiment intentionally activated a local-only application fault mode.",
        ],
        "resolution": audit.get("output", "No successful resolution was recorded."),
        "timeline": [
            {"at": investigation["observed_at"], "event": "detected", "detail": checkout_evidence},
            {"at": request.created_at, "event": "action proposed", "detail": f"{request.request_id}: {request.action}"},
            {"at": audit["started_at"], "event": "approved action started", "detail": f"approved by {audit['approver']}"},
            {"at": audit["completed_at"], "event": audit["outcome"], "detail": "; ".join(audit.get("verification", []))},
        ],
        "what_went_well": [
            "Runtime evidence identified the injected mode without granting the investigator mutation access.",
            "Unauthorized and unapproved paths were denied before execution.",
            "The approved adapter restored service and verified both fault state and health.",
        ],
        "improvements": [
            "Add an external synthetic availability probe so a green process-health endpoint cannot hide checkout failure.",
            "Export agent audit events to immutable cloud storage for production-grade retention.",
            "Replace demo identities and the local approval secret with enterprise identity and KMS-backed signing.",
        ],
        "action_items": [
            {"owner": "commerce-sre", "action": "Add checkout-path synthetic probing to the SLO signal.", "status": "planned"},
            {"owner": "platform-sre", "action": "Design immutable audit export for AWS and Azure.", "status": "planned"},
            {"owner": "security-platform", "action": "Integrate workforce identity with approval verification.", "status": "planned"},
        ],
        "evidence": {
            "request_id": request.request_id,
            "request_digest": request.digest,
            "audit_event_hash": audit["event_hash"],
            "agent": investigation["agent"],
            "approver": audit["approver"],
        },
    }


def markdown(postmortem: dict[str, Any]) -> str:
    lines = [
        f"# Postmortem: {postmortem['incident_id']}",
        "",
        f"- **Status:** {postmortem['status']}",
        f"- **Severity:** {postmortem['severity']}",
        "- **Scope:** local reliability lab; no production users",
        "",
        "## Summary",
        "",
        postmortem["summary"],
        "",
        "## Impact",
        "",
        postmortem["impact"],
        "",
        "## Detection",
        "",
        postmortem["detection"],
        "",
        "## Timeline",
        "",
        "| Time (UTC) | Event | Evidence |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {escape(item['at'])} | {escape(item['event'])} | {escape(item['detail'])} |" for item in postmortem["timeline"])
    lines.extend(["", "## Root cause", "", postmortem["root_cause"], "", "## Contributing factors", ""])
    lines.extend(f"- {item}" for item in postmortem["contributing_factors"])
    lines.extend(["", "## Resolution and verification", "", postmortem["resolution"], "", "## What went well", ""])
    lines.extend(f"- {item}" for item in postmortem["what_went_well"])
    lines.extend(["", "## Improvements", ""])
    lines.extend(f"- {item}" for item in postmortem["improvements"])
    lines.extend(["", "## Action items", "", "| Owner | Action | Status |", "| --- | --- | --- |"])
    lines.extend(f"| {escape(item['owner'])} | {escape(item['action'])} | {escape(item['status'])} |" for item in postmortem["action_items"])
    evidence = postmortem["evidence"]
    lines.extend([
        "", "## Evidence integrity", "",
        f"- Request: `{evidence['request_id']}`",
        f"- Request SHA-256: `{evidence['request_digest']}`",
        f"- Audit event SHA-256: `{evidence['audit_event_hash']}`",
        f"- Investigator: `{evidence['agent']}`",
        f"- Approver: `{evidence['approver']}`",
        "", "This is a blameless review of system behavior and control effectiveness.", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--investigation", type=Path, required=True)
    parser.add_argument("--audit-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    try:
        investigation, request, audit = load_evidence(args.investigation, args.audit_log)
        postmortem = build_postmortem(investigation, request, audit)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"FAIL postmortem: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown(postmortem))
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(postmortem, indent=2, sort_keys=True) + "\n")
    print(f"PASS postmortem generated: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
