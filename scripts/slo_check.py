#!/usr/bin/env python3
"""Simple SLO policy evaluator for CI and local reliability checks."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
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
    owner: str | None
    target: float
    budget: float
    state: str
    windows: list[WindowResult]


def _pct(value: float) -> str:
    return f"{value * 100:.4f}%"


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def evaluate_service(
    service: dict[str, Any],
    min_requests: int,
    min_requests_overrides: dict[str, int],
    warn_burn: float,
    crit_burn: float,
    require_owner: bool,
    required_windows: set[str],
    owner_email_domain: str | None,
    window_burn_overrides: dict[str, tuple[float, float]],
    expected_window_minutes: dict[str, int],
    max_insufficient_windows: int,
) -> ServiceResult:
    name = service["name"]
    target = float(service["target_availability"])

    owner_value = service.get("owner")
    owner = owner_value.strip() if isinstance(owner_value, str) else None
    if require_owner and not owner:
        raise ValueError(f"service '{name}' is missing required non-empty owner field")

    if owner_email_domain:
        if not owner:
            raise ValueError(
                f"service '{name}' must define owner when policy.owner_email_domain is set"
            )
        owner_parts = owner.rsplit("@", 1)
        if len(owner_parts) != 2 or not owner_parts[1]:
            raise ValueError(f"service '{name}' owner '{owner}' is not a valid email address")
        owner_domain = owner_parts[1].lower()
        if owner_domain != owner_email_domain:
            raise ValueError(
                f"service '{name}' owner domain '{owner_domain}' does not match required domain '{owner_email_domain}'"
            )

    if not (0 < target < 1):
        raise ValueError(f"service '{name}' has invalid target_availability={target}; expected value between 0 and 1")

    budget = 1.0 - target
    windows_data = service.get("windows", [])
    if not windows_data:
        raise ValueError(f"service '{name}' must define at least one window")

    windows: list[WindowResult] = []
    highest = "pass"
    insufficient_windows = 0
    seen_labels: set[str] = set()

    for item in windows_data:
        label = item["label"]
        minutes = int(item["minutes"])
        total = int(item["total_requests"])
        errors = int(item["error_requests"])

        if label in seen_labels:
            raise ValueError(f"service '{name}' has duplicate window label '{label}'")
        seen_labels.add(label)

        if minutes <= 0:
            raise ValueError(f"service '{name}' window '{label}' must have minutes > 0")

        expected_minutes = expected_window_minutes.get(label)
        if expected_minutes is not None and minutes != expected_minutes:
            raise ValueError(
                f"service '{name}' window '{label}' has minutes={minutes}, expected {expected_minutes}"
            )
        if total < 0 or errors < 0:
            raise ValueError(f"service '{name}' window '{label}' has negative request counts")
        if errors > total:
            raise ValueError(f"service '{name}' window '{label}' has error_requests > total_requests")

        availability = _safe_div(total - errors, total)
        burn_rate = _safe_div((1.0 - availability), budget)
        effective_warn_burn, effective_crit_burn = window_burn_overrides.get(label, (warn_burn, crit_burn))
        effective_min_requests = min_requests_overrides.get(label, min_requests)

        if total < effective_min_requests:
            state = "insufficient-data"
            insufficient_windows += 1
        elif burn_rate >= effective_crit_burn:
            state = "critical"
            highest = "critical"
        elif burn_rate >= effective_warn_burn and highest != "critical":
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

    missing_windows = sorted(required_windows - seen_labels)
    if missing_windows:
        missing = ", ".join(missing_windows)
        raise ValueError(f"service '{name}' is missing required windows: {missing}")

    if highest == "pass" and insufficient_windows > max_insufficient_windows:
        highest = "insufficient-data"

    return ServiceResult(name=name, owner=owner, target=target, budget=budget, state=highest, windows=windows)


def evaluate(data: dict[str, Any], require_owner: bool = False) -> list[ServiceResult]:
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

    required_windows = {str(label) for label in policy.get("required_windows", [])}

    max_insufficient_windows = int(policy.get("max_insufficient_windows", 0))
    if max_insufficient_windows < 0:
        raise ValueError("policy.max_insufficient_windows must be >= 0")

    min_requests_overrides_raw = policy.get("min_requests_overrides", {})
    if not isinstance(min_requests_overrides_raw, dict):
        raise ValueError("policy.min_requests_overrides must be an object mapping labels to request thresholds")

    min_requests_overrides: dict[str, int] = {}
    for label, threshold in min_requests_overrides_raw.items():
        threshold_int = int(threshold)
        if threshold_int < 0:
            raise ValueError(f"policy.min_requests_overrides['{label}'] must be >= 0")
        min_requests_overrides[str(label)] = threshold_int

    owner_email_domain_raw = policy.get("owner_email_domain")
    owner_email_domain: str | None = None
    if owner_email_domain_raw is not None:
        owner_email_domain = str(owner_email_domain_raw).strip().lower().lstrip("@")
        if not owner_email_domain:
            raise ValueError("policy.owner_email_domain must be a non-empty domain string when set")

    window_burn_overrides_raw = policy.get("window_burn_rate_overrides", {})
    if not isinstance(window_burn_overrides_raw, dict):
        raise ValueError("policy.window_burn_rate_overrides must be an object mapping labels to thresholds")

    window_burn_overrides: dict[str, tuple[float, float]] = {}
    for label, thresholds in window_burn_overrides_raw.items():
        label_str = str(label)
        if not isinstance(thresholds, dict):
            raise ValueError(
                f"policy.window_burn_rate_overrides['{label_str}'] must be an object with warning/critical burn rates"
            )

        override_warn = float(thresholds.get("warning_burn_rate", warn_burn))
        override_crit = float(thresholds.get("critical_burn_rate", crit_burn))

        if override_warn <= 0 or override_crit <= 0:
            raise ValueError(
                f"policy.window_burn_rate_overrides['{label_str}'] burn rates must be > 0"
            )
        if override_warn > override_crit:
            raise ValueError(
                f"policy.window_burn_rate_overrides['{label_str}'] warning_burn_rate cannot exceed critical_burn_rate"
            )

        window_burn_overrides[label_str] = (override_warn, override_crit)

    expected_window_minutes_raw = policy.get("window_minutes", {})
    if not isinstance(expected_window_minutes_raw, dict):
        raise ValueError("policy.window_minutes must be an object mapping labels to expected minute values")

    expected_window_minutes: dict[str, int] = {}
    for label, minutes in expected_window_minutes_raw.items():
        label_str = str(label)
        minutes_int = int(minutes)
        if minutes_int <= 0:
            raise ValueError(f"policy.window_minutes['{label_str}'] must be > 0")
        expected_window_minutes[label_str] = minutes_int

    services = data.get("services", [])
    if not services:
        raise ValueError("no services were defined")

    seen_services: set[str] = set()
    known_window_labels: set[str] = set()
    for s in services:
        name = str(s.get("name", "")).strip()
        if not name:
            raise ValueError("service is missing non-empty name")
        if name in seen_services:
            raise ValueError(f"duplicate service name '{name}'")
        seen_services.add(name)

        for window in s.get("windows", []):
            label = str(window.get("label", "")).strip()
            if label:
                known_window_labels.add(label)

    override_label_sources = {
        "policy.min_requests_overrides": set(min_requests_overrides.keys()),
        "policy.window_burn_rate_overrides": set(window_burn_overrides.keys()),
        "policy.window_minutes": set(expected_window_minutes.keys()),
    }
    for source_name, labels in override_label_sources.items():
        unknown_labels = sorted(labels - known_window_labels)
        if unknown_labels:
            raise ValueError(
                f"{source_name} contains unknown window labels: {', '.join(unknown_labels)}"
            )

    return [
        evaluate_service(
            s,
            min_requests=min_requests,
            min_requests_overrides=min_requests_overrides,
            warn_burn=warn_burn,
            crit_burn=crit_burn,
            require_owner=require_owner,
            required_windows=required_windows,
            owner_email_domain=owner_email_domain,
            window_burn_overrides=window_burn_overrides,
            expected_window_minutes=expected_window_minutes,
            max_insufficient_windows=max_insufficient_windows,
        )
        for s in services
    ]


def render(results: Iterable[ServiceResult]) -> str:
    lines: list[str] = []
    for service in results:
        lines.append(f"Service: {service.name}")
        lines.append(f"  Owner : {service.owner or 'unknown'}")
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


def to_json(results: Iterable[ServiceResult]) -> str:
    payload = [asdict(result) for result in results]
    return json.dumps(payload, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate SLO error-budget burn for one or more services.")
    parser.add_argument("--input", "-i", type=Path, default=Path("projects/01-slo-engine/sample-slo.json"), help="path to SLO policy JSON")
    parser.add_argument("--output", choices=("text", "json"), default="text", help="render output as text table or machine-readable JSON")
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="return non-zero on warning (default only fails on critical)",
    )
    parser.add_argument(
        "--fail-on-insufficient-data",
        action="store_true",
        help="return non-zero when any window is marked insufficient-data (useful for CI quality gates)",
    )
    parser.add_argument(
        "--require-owner",
        action="store_true",
        help="return non-zero if any service omits a non-empty owner field",
    )
    args = parser.parse_args()

    try:
        data = json.loads(args.input.read_text())
        results = evaluate(data, require_owner=args.require_owner)
    except Exception as exc:  # broad by design: CI should fail with clear error
        print(f"slo-check: failed to evaluate policy: {exc}", file=sys.stderr)
        return 2

    if args.output == "json":
        print(to_json(results))
    else:
        print(render(results))

    if any(r.state == "critical" for r in results):
        return 1
    if args.fail_on_warning and any(r.state == "warning" for r in results):
        return 1
    if args.fail_on_insufficient_data and any(
        window.state == "insufficient-data" for service in results for window in service.windows
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
