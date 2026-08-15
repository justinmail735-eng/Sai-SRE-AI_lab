#!/usr/bin/env python3
"""Approve, execute, and audit narrowly allowlisted SRE actions."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.governance import (
    ActionRequest,
    Approval,
    AuditLog,
    GovernancePolicy,
    IdentityRegistry,
    create_approval,
    utc_now,
    verify_approval,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "agents/policy/governance.json"
DEFAULT_IDENTITIES = ROOT / "agents/identities/demo-identities.json"


def load_request(path: Path) -> ActionRequest:
    return ActionRequest.from_dict(json.loads(path.read_text()))


def load_approval(path: Path) -> Approval:
    return Approval.from_dict(json.loads(path.read_text()))


def execute_action(request: ActionRequest, runner: Callable[..., Any] = subprocess.run) -> str:
    if request.action == "fault.recover":
        base_url = request.parameters["base_url"].rstrip("/")
        endpoint = f"{base_url}/admin/fault?{urllib.parse.urlencode({'mode': 'none'})}"
        try:
            with urllib.request.urlopen(urllib.request.Request(endpoint, method="POST"), timeout=5) as response:
                if response.status != 200:
                    raise RuntimeError(f"recovery endpoint returned HTTP {response.status}")
                return "checkout fault mode set to none"
        except urllib.error.URLError as exc:
            raise RuntimeError(f"recovery endpoint failed: {exc}") from exc

    namespace, deployment = request.target.split("/", maxsplit=1)
    if request.action == "kubernetes.restart":
        command = ["kubectl", "rollout", "restart", f"deployment/{deployment}", "--namespace", namespace]
    elif request.action == "kubernetes.scale":
        command = [
            "kubectl", "scale", f"deployment/{deployment}", "--namespace", namespace,
            f"--replicas={request.parameters['replicas']}",
        ]
    else:
        raise ValueError(f"no execution adapter for '{request.action}'")
    result = runner(command, check=True, text=True, capture_output=True)
    return result.stdout.strip() or "command completed"


def verify_effect(request: ActionRequest) -> list[str]:
    if request.action == "fault.recover":
        base_url = request.parameters["base_url"].rstrip("/")
        with urllib.request.urlopen(f"{base_url}/metrics", timeout=5) as response:
            metrics = response.read().decode()
        if not re.search(
            r'^sentinel_sre_fault_mode\{[^}]*mode="none"[^}]*\}\s+1(?:\.0)?$',
            metrics,
            flags=re.MULTILINE,
        ):
            raise RuntimeError("fault mode did not return to none")
        with urllib.request.urlopen(f"{base_url}/healthz", timeout=5) as response:
            if response.status != 200:
                raise RuntimeError("health verification failed")
        return ["fault mode is none", "health endpoint returned HTTP 200"]

    namespace, deployment = request.target.split("/", maxsplit=1)
    result = subprocess.run(
        ["kubectl", "rollout", "status", f"deployment/{deployment}", "--namespace", namespace, "--timeout=2m"],
        check=True, text=True, capture_output=True,
    )
    return [result.stdout.strip()]


def approve(args: argparse.Namespace) -> int:
    request = load_request(args.request)
    policy = GovernancePolicy.load(args.policy)
    policy.validate(request, apply=True)
    IdentityRegistry.load(args.identities).require_approver(args.approver, policy, request.environment)
    secret = os.environ.get("SENTINELSRE_APPROVAL_KEY", "")
    approval = create_approval(request, args.approver, secret, ttl_minutes=args.ttl_minutes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(approval.to_dict(), indent=2, sort_keys=True) + "\n")
    print(f"APPROVED {request.request_id} by {args.approver}; expires {approval.expires_at}")
    return 0


def execute(args: argparse.Namespace) -> int:
    request = load_request(args.request)
    policy = GovernancePolicy.load(args.policy)
    action_policy = policy.validate(request, apply=args.apply)
    if not args.apply:
        print(json.dumps({
            "request_id": request.request_id,
            "decision": "dry-run",
            "approval_required": True,
            "action_policy": action_policy,
            "changes_applied": False,
        }, indent=2, sort_keys=True))
        return 0

    if args.approval is None:
        raise ValueError("--approval is required with --apply")
    approval = load_approval(args.approval)
    IdentityRegistry.load(args.identities).require_approver(approval.approver, policy, request.environment)
    verify_approval(request, approval, os.environ.get("SENTINELSRE_APPROVAL_KEY", ""))
    audit = AuditLog(args.audit_log)
    started_at = utc_now().isoformat().replace("+00:00", "Z")
    try:
        output = execute_action(request)
        verification = verify_effect(request)
        outcome = "succeeded"
    except Exception as exc:
        output = str(exc)
        verification = []
        outcome = "failed"
    record = audit.append({
        "api_version": "sentinelsre.io/v1",
        "kind": "ActionAuditEvent",
        "request_id": request.request_id,
        "request_digest": request.digest,
        "incident_id": request.incident_id,
        "action": request.action,
        "target": request.target,
        "requester": request.requester,
        "approver": approval.approver,
        "started_at": started_at,
        "completed_at": utc_now().isoformat().replace("+00:00", "Z"),
        "outcome": outcome,
        "output": output,
        "verification": verification,
    })
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0 if outcome == "succeeded" else 1


def verify_audit(args: argparse.Namespace) -> int:
    audit = AuditLog(args.audit_log)
    audit.verify()
    print(f"PASS audit chain: {len(audit.records())} record(s)")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    approval = commands.add_parser("approve")
    approval.add_argument("--request", type=Path, required=True)
    approval.add_argument("--approver", required=True)
    approval.add_argument("--ttl-minutes", type=int, default=15)
    approval.add_argument("--output", type=Path, required=True)
    approval.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    approval.add_argument("--identities", type=Path, default=DEFAULT_IDENTITIES)
    approval.set_defaults(handler=approve)

    execution = commands.add_parser("execute")
    execution.add_argument("--request", type=Path, required=True)
    execution.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    execution.add_argument("--approval", type=Path)
    execution.add_argument("--identities", type=Path, default=DEFAULT_IDENTITIES)
    execution.add_argument("--audit-log", type=Path, default=ROOT / "build/audit/actions.jsonl")
    execution.add_argument("--apply", action="store_true")
    execution.set_defaults(handler=execute)

    audit = commands.add_parser("verify-audit")
    audit.add_argument("--audit-log", type=Path, default=ROOT / "build/audit/actions.jsonl")
    audit.set_defaults(handler=verify_audit)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"DENIED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
