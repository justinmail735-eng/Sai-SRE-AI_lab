#!/usr/bin/env python3
"""Render and enforce SentinelSRE Kubernetes workload invariants."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHART = ROOT / "platform" / "helm" / "checkout-api"

REQUIRED_DOCUMENTS = {
    "kind: Deployment",
    "kind: Service",
    "kind: ServiceAccount",
    "kind: HorizontalPodAutoscaler",
    "kind: PodDisruptionBudget",
    "kind: NetworkPolicy",
}

REQUIRED_SAFEGUARDS = {
    "runAsNonRoot: true": "non-root pod execution",
    "allowPrivilegeEscalation: false": "privilege escalation disabled",
    "readOnlyRootFilesystem: true": "read-only root filesystem",
    "seccompProfile:": "seccomp profile",
    "drop:": "capability drop",
    "startupProbe:": "startup probe",
    "readinessProbe:": "readiness probe",
    "livenessProbe:": "liveness probe",
    "resources:": "resource controls",
    "maxUnavailable: 0": "zero-unavailable rolling update",
    "topologySpreadConstraints:": "topology spreading",
    "automountServiceAccountToken: false": "service-account token disabled",
}


def render(chart: Path, values: Path | None = None) -> str:
    command = ["helm", "template", "sentinel", str(chart), "--namespace", "sentinelsre"]
    if values:
        command.extend(["--values", str(values)])
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip())
    return completed.stdout


def validate(rendered: str) -> list[str]:
    errors = []
    for marker in sorted(REQUIRED_DOCUMENTS):
        if marker not in rendered:
            errors.append(f"missing resource: {marker.removeprefix('kind: ')}")
    for marker, description in REQUIRED_SAFEGUARDS.items():
        if marker not in rendered:
            errors.append(f"missing safeguard: {description}")
    if "image: \"local-checkout-api:latest\"" not in rendered:
        errors.append("workload image is not explicitly configured")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chart", type=Path, default=DEFAULT_CHART)
    parser.add_argument("--values", type=Path)
    args = parser.parse_args()
    try:
        rendered = render(args.chart, args.values)
    except (OSError, RuntimeError) as exc:
        print(f"FAIL helm render: {exc}", file=sys.stderr)
        return 2
    errors = validate(rendered)
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("PASS Helm chart renders all required resources")
    print("PASS Kubernetes workload safeguards are present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
