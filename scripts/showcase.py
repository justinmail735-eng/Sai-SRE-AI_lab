#!/usr/bin/env python3
"""Run the complete SentinelSRE enterprise showcase and emit an evidence report."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build/showcase"
ACKNOWLEDGEMENT = "LOCAL-DEMO-ONLY"
REQUIRED_TOOLS = ("docker", "helm", "kind", "kubectl", "terraform", "tflint", "kustomize", "conftest", "trivy", "syft", "npm")


@dataclass
class Check:
    name: str
    capability: str
    passed: bool
    duration_seconds: float
    evidence: str


@dataclass
class Showcase:
    started_at: str
    checks: list[Check] = field(default_factory=list)
    created_cluster: bool = False
    execution_failed: bool = False

    @property
    def passed(self) -> bool:
        return bool(self.checks) and not self.execution_failed and all(check.passed for check in self.checks)

    def record(self, name: str, capability: str, started: float, passed: bool, evidence: str) -> None:
        self.checks.append(Check(name, capability, passed, round(time.monotonic() - started, 3), evidence.strip()[-1200:]))


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def command(args: list[str], *, env: dict[str, str] | None = None, expected: int = 0) -> str:
    completed = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, env=env)
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    if completed.returncode != expected:
        raise RuntimeError(f"{' '.join(args)} returned {completed.returncode}, expected {expected}\n{output}")
    return output


def run_check(showcase: Showcase, name: str, capability: str, args: list[str]) -> None:
    started = time.monotonic()
    try:
        evidence = command(args)
        showcase.record(name, capability, started, True, evidence or "command passed")
        print(f"PASS {name}")
    except RuntimeError as exc:
        showcase.record(name, capability, started, False, str(exc))
        raise


def post_fault(mode: str) -> None:
    endpoint = f"http://127.0.0.1:8080/admin/fault?{urllib.parse.urlencode({'mode': mode})}"
    with urllib.request.urlopen(urllib.request.Request(endpoint, method="POST"), timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"fault endpoint returned HTTP {response.status}")


def ensure_local_stack(showcase: Showcase) -> None:
    run_check(
        showcase,
        "live-observability-stack",
        "instrumented workload and observability",
        ["docker", "compose", "-f", "observability/local/docker-compose.yml", "up", "--build", "-d"],
    )
    run_check(showcase, "telemetry-path", "instrumented workload and observability", [sys.executable, "scripts/live_stack_check.py"])


def ensure_kind(showcase: Showcase) -> None:
    clusters = command(["kind", "get", "clusters"])
    if "sentinelsre" not in clusters.splitlines():
        command(["kind", "create", "cluster", "--config", "platform/kind/cluster.yaml"])
        showcase.created_cluster = True
    context = command(["kubectl", "config", "current-context"])
    if context != "kind-sentinelsre":
        raise RuntimeError(f"refusing Kubernetes demo on context '{context}'; expected kind-sentinelsre")
    command(["docker", "build", "-t", "local-checkout-api:latest", "applications/checkout-api"])
    command(["kind", "load", "docker-image", "local-checkout-api:latest", "--name", "sentinelsre"])
    namespace = subprocess.run(
        ["kubectl", "get", "namespace", "sentinelsre"], cwd=ROOT, text=True, capture_output=True
    )
    if namespace.returncode != 0:
        command(["kubectl", "create", "namespace", "sentinelsre"])
    command([
        "helm", "upgrade", "--install", "checkout", "platform/helm/checkout-api",
        "--namespace", "sentinelsre", "--values", "platform/helm/checkout-api/values-kind.yaml",
        "--wait", "--timeout", "3m",
    ])


def governed_incident(showcase: Showcase) -> None:
    incident_dir = OUTPUT / "incident"
    incident_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    post_fault("errors")
    try:
        command([
            sys.executable, "agents/incident_investigator.py", "--base-url", "http://127.0.0.1:8080",
            "--incident-id", "INC-SHOWCASE", "--output", str(incident_dir / "investigation.json"),
        ])
        request = incident_dir / "action-request.json"
        denied = command(
            [sys.executable, "agents/action_broker.py", "execute", "--request", str(request), "--apply"],
            expected=2,
        )
        if "--approval is required" not in denied:
            raise RuntimeError("unapproved execution did not produce the expected denial")

        key = secrets.token_urlsafe(32)
        broker_env = {**os.environ, "SENTINELSRE_APPROVAL_KEY": key}
        observer = command([
            sys.executable, "agents/action_broker.py", "approve", "--request", str(request),
            "--approver", "alex.observer", "--output", str(incident_dir / "observer-approval.json"),
        ], env=broker_env, expected=2)
        if "lacks an authorized role" not in observer:
            raise RuntimeError("observer approval did not produce the expected denial")

        approval = incident_dir / "approval.json"
        command([
            sys.executable, "agents/action_broker.py", "approve", "--request", str(request),
            "--approver", "sai.demo", "--output", str(approval),
        ], env=broker_env)
        audit = incident_dir / "actions.jsonl"
        execution = command([
            sys.executable, "agents/action_broker.py", "execute", "--request", str(request),
            "--approval", str(approval), "--audit-log", str(audit), "--apply",
        ], env=broker_env)
        command([sys.executable, "agents/action_broker.py", "verify-audit", "--audit-log", str(audit)])
        command([
            sys.executable, "scripts/postmortem_generator.py", "--investigation", str(incident_dir / "investigation.json"),
            "--audit-log", str(audit), "--output", str(incident_dir / "postmortem.md"),
            "--json-output", str(incident_dir / "postmortem.json"),
        ])
        outcome = json.loads(execution)["outcome"]
        if outcome != "succeeded":
            raise RuntimeError(f"governed recovery outcome was {outcome}")
        showcase.record(
            "governed-incident-recovery", "governed SRE agents", started, True,
            "503 detected; unapproved apply denied; observer denied; incident commander approved; recovery and audit verified",
        )
        print("PASS governed-incident-recovery")
    finally:
        post_fault("none")


def render_report(showcase: Showcase) -> str:
    status = "PASS" if showcase.passed else "FAIL"
    lines = [
        "# SentinelSRE Enterprise Showcase Report", "",
        f"- **Outcome:** {status}",
        f"- **Started:** {showcase.started_at}",
        f"- **Completed:** {iso_now()}",
        f"- **Checks:** {sum(item.passed for item in showcase.checks)}/{len(showcase.checks)} passed",
        "- **Safety scope:** local Docker and `kind-sentinelsre`; no cloud apply or production mutation",
        "", "## Capability evidence", "",
        "| Capability | Check | Result | Duration |",
        "| --- | --- | --- | ---: |",
    ]
    lines.extend(
        f"| {item.capability} | {item.name} | {'PASS' if item.passed else 'FAIL'} | {item.duration_seconds:.3f}s |"
        for item in showcase.checks
    )
    lines.extend(["", "## Evidence details", ""])
    for item in showcase.checks:
        lines.extend([f"### {item.name}", "", "```text", item.evidence or "passed", "```", ""])
    lines.extend([
        "## Demonstrated boundary", "",
        "AWS and Azure Terraform configurations were initialized, schema-validated, linted, and tested with mocked plans. "
        "The showcase does not create paid cloud resources or claim live cloud telemetry.", "",
    ])
    return "\n".join(lines)


def cleanup(showcase: Showcase) -> None:
    post_fault("none")
    command(["docker", "compose", "-f", "observability/local/docker-compose.yml", "down", "--volumes", "--remove-orphans"])
    if showcase.created_cluster:
        command(["kind", "delete", "cluster", "--name", "sentinelsre"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acknowledge", required=True, help=f"must be {ACKNOWLEDGEMENT}")
    parser.add_argument("--cleanup", action="store_true", help="stop the stack and delete a cluster created by this run")
    args = parser.parse_args()
    if args.acknowledge != ACKNOWLEDGEMENT:
        parser.error(f"--acknowledge must be {ACKNOWLEDGEMENT}")
    missing = [tool for tool in REQUIRED_TOOLS if not shutil.which(tool)]
    if missing:
        parser.error("missing required tools: " + ", ".join(missing))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    showcase = Showcase(started_at=iso_now())
    try:
        run_check(showcase, "unit-and-behavior-tests", "tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-q"])
        run_check(showcase, "continuous-reliability", "continuous checks", [sys.executable, "scripts/reliability_check.py"])
        run_check(showcase, "terraform-foundations", "AWS and Azure Terraform", [sys.executable, "scripts/terraform_validate.py"])
        run_check(showcase, "gitops-admission", "GitOps and policy", [sys.executable, "scripts/gitops_validate.py"])
        run_check(showcase, "supply-chain", "software supply chain", ["make", "security-check"])
        started = time.monotonic()
        site_evidence = command(["npm", "--prefix", "web", "test"])
        site_evidence += "\n" + command(["npm", "--prefix", "web", "run", "lint"])
        showcase.record("portfolio-site", "interview presentation", started, True, site_evidence)
        print("PASS portfolio-site")
        ensure_local_stack(showcase)
        governed_incident(showcase)
        started = time.monotonic()
        ensure_kind(showcase)
        command([sys.executable, "scripts/k8s_runtime_check.py"])
        showcase.record("kubernetes-runtime", "Kubernetes and Helm", started, True, "hardened multi-node workload is healthy and reachable")
        print("PASS kubernetes-runtime")
        run_check(showcase, "single-pod-loss", "chaos and recovery", [
            sys.executable, "scripts/k8s_chaos_check.py", "--execute",
            "--acknowledge", "DELETE-ONE-LOCAL-CHECKOUT-POD", "--output", str(OUTPUT / "k8s-chaos.json"),
        ])
        run_check(showcase, "post-chaos-runtime", "chaos and recovery", [sys.executable, "scripts/k8s_runtime_check.py"])
    except Exception as exc:
        showcase.execution_failed = True
        print(f"FAIL showcase: {exc}", file=sys.stderr)
    finally:
        report = render_report(showcase)
        (OUTPUT / "REPORT.md").write_text(report)
        (OUTPUT / "result.json").write_text(json.dumps({
            "started_at": showcase.started_at,
            "completed_at": iso_now(),
            "passed": showcase.passed,
            "checks": [item.__dict__ for item in showcase.checks],
        }, indent=2, sort_keys=True) + "\n")
        print(f"Showcase report: {OUTPUT / 'REPORT.md'}")
        if args.cleanup:
            try:
                cleanup(showcase)
            except Exception as exc:
                print(f"WARN cleanup incomplete: {exc}", file=sys.stderr)
    return 0 if showcase.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
