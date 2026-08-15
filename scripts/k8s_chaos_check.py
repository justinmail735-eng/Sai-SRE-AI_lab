#!/usr/bin/env python3
"""Run a tightly scoped Pod-loss resilience experiment in the local Kind lab."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = "kind-sentinelsre"
NAMESPACE = "sentinelsre"
DEPLOYMENT = "checkout-checkout-api"
LABEL = "app.kubernetes.io/instance=checkout,app.kubernetes.io/name=checkout-api"
ACKNOWLEDGEMENT = "DELETE-ONE-LOCAL-CHECKOUT-POD"


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def validate_preconditions(context: str, deployment: dict[str, Any], pdb: dict[str, Any], pods: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if context != CONTEXT:
        failures.append(f"current context must be {CONTEXT}, got {context}")
    replicas = deployment.get("status", {}).get("readyReplicas", 0)
    desired = deployment.get("spec", {}).get("replicas", 0)
    if desired < 2 or replicas != desired:
        failures.append(f"deployment must have at least two ready replicas, got {replicas}/{desired}")
    min_available = pdb.get("spec", {}).get("minAvailable")
    if min_available not in (1, "1"):
        failures.append(f"PDB minAvailable must be 1, got {min_available}")
    pod_items = pods.get("items", [])
    ready_pods = [
        pod
        for pod in pod_items
        if any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in pod.get("status", {}).get("conditions", [])
        )
    ]
    if len(ready_pods) < 2:
        failures.append(f"at least two ready Pods are required, got {len(ready_pods)}")
    nodes = {pod.get("spec", {}).get("nodeName") for pod in ready_pods}
    if len(nodes) < 2:
        failures.append("ready Pods must be spread across at least two nodes")
    return failures


def select_victim(pods: dict[str, Any]) -> str:
    candidates = sorted(pod["metadata"]["name"] for pod in pods.get("items", []))
    if len(candidates) < 2:
        raise ValueError("refusing chaos: fewer than two candidate Pods")
    return candidates[0]


def snapshot() -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    context = subprocess.run(
        ["kubectl", "config", "current-context"], check=True, text=True, capture_output=True
    ).stdout.strip()
    deployment = run_json(["kubectl", "get", "deployment", DEPLOYMENT, "--namespace", NAMESPACE, "-o", "json"])
    pdb = run_json(["kubectl", "get", "pdb", DEPLOYMENT, "--namespace", NAMESPACE, "-o", "json"])
    pods = run_json(["kubectl", "get", "pods", "--namespace", NAMESPACE, "--selector", LABEL, "-o", "json"])
    return context, deployment, pdb, pods


def run_experiment(execute: bool, acknowledgement: str, timeout_seconds: int = 120) -> dict[str, Any]:
    context, deployment, pdb, pods = snapshot()
    failures = validate_preconditions(context, deployment, pdb, pods)
    if failures:
        raise ValueError("; ".join(failures))
    victim = select_victim(pods)
    original_uids = {pod["metadata"]["uid"] for pod in pods["items"]}
    timeline = [{"at": timestamp(), "event": "preflight_passed", "detail": f"2+ ready replicas protected by PDB on {context}"}]
    result: dict[str, Any] = {
        "api_version": "sentinelsre.io/v1",
        "kind": "ChaosExperimentResult",
        "experiment": "single-pod-loss",
        "scope": {"context": context, "namespace": NAMESPACE, "deployment": DEPLOYMENT, "victim": victim},
        "mode": "execute" if execute else "plan",
        "timeline": timeline,
        "recovered": False,
    }
    if not execute:
        timeline.append({"at": timestamp(), "event": "planned", "detail": f"would delete only Pod {victim}"})
        return result
    if acknowledgement != ACKNOWLEDGEMENT:
        raise ValueError(f"execution requires --acknowledge {ACKNOWLEDGEMENT}")

    subprocess.run(
        ["kubectl", "delete", "pod", victim, "--namespace", NAMESPACE, "--wait=false"],
        check=True, text=True, capture_output=True,
    )
    timeline.append({"at": timestamp(), "event": "fault_injected", "detail": f"deleted exactly one Pod: {victim}"})

    deadline = time.monotonic() + timeout_seconds
    last_detail = "replacement not observed"
    while time.monotonic() < deadline:
        _, current_deployment, _, current_pods = snapshot()
        current_uids = {pod["metadata"]["uid"] for pod in current_pods["items"]}
        ready = current_deployment.get("status", {}).get("readyReplicas", 0)
        desired = current_deployment.get("spec", {}).get("replicas", 0)
        replacement = bool(current_uids - original_uids)
        last_detail = f"ready={ready}/{desired}, replacement_observed={replacement}"
        if desired >= 2 and ready == desired and replacement:
            result["recovered"] = True
            result["recovery_seconds"] = round(timeout_seconds - (deadline - time.monotonic()), 3)
            timeline.append({"at": timestamp(), "event": "recovered", "detail": last_detail})
            return result
        time.sleep(1)
    timeline.append({"at": timestamp(), "event": "recovery_timeout", "detail": last_detail})
    raise RuntimeError(f"cluster did not recover within {timeout_seconds}s: {last_detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge", default="")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = run_experiment(args.execute, args.acknowledge, args.timeout_seconds)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"FAIL Kubernetes chaos: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if (not args.execute or result["recovered"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
