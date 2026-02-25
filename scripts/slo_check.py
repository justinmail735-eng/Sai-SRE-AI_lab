#!/usr/bin/env python3
"""Simple SLO policy evaluator for CI and local reliability checks."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass
class WindowResult:
    label: str
    minutes: int
    total_requests: int
    error_requests: int
    availability: float
    burn_rate: float
    state: str


@dataclass
class ServiceResult:
    name: str
    target: float
    budget: float
    state: str
    windows: list[WindowResult]


def _pct(value: float) -> str:
    return f"{value * 100:.4f}%"


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def evaluate_service(service: dict[str, Any], min_requests: int, warn_burn: float, crit_burn: float) -> ServiceResult:
    name = service["name"]
    target = float(service["target_availability"])

    if not (0 < target < 1):
        raise ValueError(f"service '{name}' has invalid target_availability={target}; expected value between 0 and 1")

    budget = 1.0 - target
    windows_data = service.get("windows", [])
    windows: list[WindowResult] = []
    highest = "pass"

    for item in windows_data:
        label = item["label"]
        minutes = int(item["minutes"])
        total = int(item["total_requests"])
        errors = int(item["error_requests"])

        if total < 0 or errors < 0:
            raise ValueError(f"service '{name}' window '{label}' has negative request counts")
        if errors > total:
            raise ValueError(f"service '{name}' window '{label}' has error_requests > total_requests")

        availability = _safe_div(total - errors, total)
        burn_rate = _safe_div((1.0 - availability), budget)

        if total < min_requests:
            state = "insufficient-data"
        elif burn_rate >= crit_burn:
            state = "critical"
            highest = "critical"
        elif burn_rate >= warn_burn and highest != "critical":
            state = "warning"
            highest = "warning"
        else:
            state = "pass"

        windows.append(
            WindowResult(
                label=label,
                minutes=minutes,
                total_requests=total,
                error_requests=errors,
                availability=availability,
                burn_rate=burn_rate,
                state=state,
            )
        )

    return ServiceResult(name=name, target=target, budget=budget, state=highest, windows=windows)


def evaluate(data: dict[str, Any]) -> list[ServiceResult]:
    policy = data.get("policy", {})
    min_requests = int(policy.get("min_requests", 100))
    warn_burn = float(policy.get("warning_burn_rate", 1.0))
    crit_burn = float(policy.get("critical_burn_rate", 2.0))

    if min_requests < 0:
        raise ValueError("policy.min_requests must be >= 0")
    if warn_burn <= 0 or crit_burn <= 0:
        raise ValueError("policy burn rates must be > 0")
    if warn_burn > crit_burn:
        raise ValueError("policy.warning_burn_rate cannot exceed policy.critical_burn_rate")

    services = data.get("services", [])
    if not services:
        raise ValueError("no services were defined")

    return [evaluate_service(s, min_requests=min_requests, warn_burn=warn_burn, crit_burn=crit_burn) for s in services]


def render(results: Iterable[ServiceResult]) -> str:
    lines: list[str] = []
    for service in results:
        lines.append(f"Service: {service.name}")
        lines.append(f"  Target: {_pct(service.target)} (budget {_pct(service.budget)})")
        lines.append(f"  State : {service.state.upper()}")
        lines.append("  Windows:")

        for w in service.windows:
            burn = "inf" if math.isinf(w.burn_rate) else f"{w.burn_rate:.2f}x"
            lines.append(
                "    - "
                f"{w.label:>4} ({w.minutes:>4}m) | "
                f"availability={_pct(w.availability):>10} | "
                f"burn={burn:>6} | "
                f"state={w.state}"
            )
        lines.append("")

    return "\n".join(lines).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate SLO error-budget burn for one or more services.")
    parser.add_argument("--input", "-i", type=Path, default=Path("projects/01-slo-engine/sample-slo.json"), help="path to SLO policy JSON")
    args = parser.parse_args()

    try:
        data = json.loads(args.input.read_text())
        results = evaluate(data)
    except Exception as exc:  # broad by design: CI should fail with clear error
        print(f"slo-check: failed to evaluate policy: {exc}", file=sys.stderr)
        return 2

    print(render(results))

    if any(r.state == "critical" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
