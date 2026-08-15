#!/usr/bin/env python3
"""Validate committed drill evidence and generated postmortem drift."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.postmortem_generator import build_postmortem, load_evidence, markdown

INCIDENT = ROOT / "docs/evidence/INC-DEMO-ERROR"
POSTMORTEM = ROOT / "docs/postmortems/INC-DEMO-ERROR.md"
CHAOS = ROOT / "docs/evidence/K8S-POD-LOSS/result.json"


def main() -> int:
    investigation, request, audit = load_evidence(INCIDENT / "investigation.json", INCIDENT / "actions.jsonl")
    expected = build_postmortem(investigation, request, audit)
    if json.loads((INCIDENT / "postmortem.json").read_text()) != expected:
        raise ValueError("postmortem JSON is stale or modified")
    if POSTMORTEM.read_text() != markdown(expected):
        raise ValueError("postmortem Markdown is stale or modified")
    if expected["status"] != "resolved" or "No production users" not in expected["impact"]:
        raise ValueError("application drill scope or outcome is invalid")

    chaos = json.loads(CHAOS.read_text())
    if chaos.get("kind") != "ChaosExperimentResult" or chaos.get("mode") != "execute":
        raise ValueError("Kubernetes chaos evidence is not an executed experiment")
    if not chaos.get("recovered") or not 0 < chaos.get("recovery_seconds", 0) <= 120:
        raise ValueError("Kubernetes chaos evidence does not prove bounded recovery")
    scope = chaos.get("scope", {})
    if scope.get("context") != "kind-sentinelsre" or scope.get("namespace") != "sentinelsre":
        raise ValueError("Kubernetes chaos evidence escaped the local scope")
    events = [item.get("event") for item in chaos.get("timeline", [])]
    if events != ["preflight_passed", "fault_injected", "recovered"]:
        raise ValueError("Kubernetes chaos timeline is incomplete")

    print("PASS application incident evidence and audit binding")
    print("PASS generated postmortem drift")
    print("PASS Kubernetes Pod-loss recovery evidence")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"FAIL evidence: {exc}", file=sys.stderr)
        raise SystemExit(1)
