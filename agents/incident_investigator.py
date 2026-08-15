#!/usr/bin/env python3
"""Investigate the live checkout lab and draft a governed recovery request."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.governance import ActionRequest, utc_now


def fetch(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        exc.close()
        return exc.code, body


def active_fault(metrics: str) -> str:
    for mode in ("errors", "latency", "none"):
        pattern = rf'^sentinel_sre_fault_mode\{{[^}}]*mode="{mode}"[^}}]*\}}\s+1(?:\.0)?$'
        if re.search(pattern, metrics, flags=re.MULTILINE):
            return mode
    return "unknown"


def investigate(base_url: str, incident_id: str, created_at: str | None = None) -> dict:
    base_url = base_url.rstrip("/")
    health_status, health_body = fetch(f"{base_url}/healthz")
    checkout_status, checkout_body = fetch(f"{base_url}/checkout")
    metrics_status, metrics = fetch(f"{base_url}/metrics")
    mode = active_fault(metrics) if metrics_status == 200 else "unknown"
    evidence = [
        f"GET /healthz returned HTTP {health_status}: {health_body.strip()[:120]}",
        f"GET /checkout returned HTTP {checkout_status}: {checkout_body.strip()[:120]}",
        f"checkout_fault_mode reports {mode}",
    ]
    report = {
        "api_version": "sentinelsre.io/v1",
        "kind": "IncidentInvestigation",
        "incident_id": incident_id,
        "agent": "IncidentInvestigatorAgent",
        "mode": "read-only",
        "evidence": evidence,
        "hypotheses": [],
        "recommended_action": None,
    }
    if mode in {"errors", "latency"}:
        report["hypotheses"] = [{
            "summary": f"local demo fault injection is set to {mode}",
            "confidence": 0.99,
            "supporting_evidence": [evidence[2]],
            "contradicting_evidence": [evidence[0]] if health_status == 200 else [],
        }]
        request = ActionRequest(
            api_version="sentinelsre.io/v1",
            kind="ActionRequest",
            incident_id=incident_id,
            requester="IncidentInvestigatorAgent",
            environment="local",
            action="fault.recover",
            target="checkout-api",
            parameters={"base_url": base_url},
            risk="medium",
            evidence=evidence,
            verification=["fault mode equals none", "health endpoint returns HTTP 200"],
            rollback="No rollback: restoring an intentionally injected failure is unsafe; re-injection remains a separate approved demo action.",
            created_at=created_at or utc_now().isoformat().replace("+00:00", "Z"),
        )
        report["recommended_action"] = {"request_id": request.request_id, **request.to_dict()}
    else:
        report["hypotheses"] = [{
            "summary": "no active controlled fault was identified",
            "confidence": 0.9 if mode == "none" else 0.2,
            "supporting_evidence": evidence,
            "contradicting_evidence": [],
        }]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = investigate(args.base_url, args.incident_id)
    except (OSError, urllib.error.URLError) as exc:
        print(f"ERROR: investigation failed: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    recommendation = report["recommended_action"]
    if recommendation:
        request_path = args.output.with_name("action-request.json")
        request_path.write_text(json.dumps({key: value for key, value in recommendation.items() if key != "request_id"}, indent=2, sort_keys=True) + "\n")
        print(f"PROPOSED {recommendation['request_id']} -> {request_path}")
    else:
        print("NO ACTION: no active controlled fault identified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
