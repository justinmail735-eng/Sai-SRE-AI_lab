#!/usr/bin/env python3
"""Incident Simulator — generate fault injection scenarios and incident timelines.

Fault types
-----------
latency_spike        — service p99 latency exceeds SLO threshold
error_rate           — elevated 5xx rate burns error budget
dependency_timeout   — upstream dependency stops responding
cascade              — downstream failures propagate across services

Usage
-----
    python scripts/incident_sim.py --fault-type error_rate --service payments-api
    python scripts/incident_sim.py --fault-type cascade --severity P1 --output json
    python scripts/incident_sim.py --list-runbooks
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import random
import sys
from dataclasses import asdict, dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAULT_TYPES = ("latency_spike", "error_rate", "dependency_timeout", "cascade")

SEVERITY_LEVELS = ("P1", "P2", "P3", "P4")

# Default fault → severity mapping when not explicitly set
FAULT_DEFAULT_SEVERITY: dict[str, str] = {
    "latency_spike": "P3",
    "error_rate": "P2",
    "dependency_timeout": "P2",
    "cascade": "P1",
}

# Runbooks keyed by (fault_type, severity) with fallback to (fault_type, None)
RUNBOOKS: dict[tuple[str, str | None], str] = {
    ("latency_spike", None): (
        "1. Check p99 latency dashboards for the affected service.\n"
        "2. Review recent deployments (rollback if correlated).\n"
        "3. Check downstream dependencies for saturation.\n"
        "4. If DB: run EXPLAIN on slow queries; check connection pool.\n"
        "5. Enable request shedding / rate limiting if latency > 5× SLO."
    ),
    ("error_rate", None): (
        "1. Identify the error class (4xx vs 5xx) from logs.\n"
        "2. Correlate with recent deployments or config pushes.\n"
        "3. Check upstream caller retry storms amplifying the rate.\n"
        "4. If 503/504: inspect load balancer health checks.\n"
        "5. Roll back if burn rate > 2× and cause is unknown."
    ),
    ("dependency_timeout", None): (
        "1. Confirm timeout scope: single host or entire dependency?\n"
        "2. Check network path (VPC routing, security groups, DNS).\n"
        "3. Verify the dependency's own health endpoint.\n"
        "4. Enable circuit breaker / fallback if available.\n"
        "5. Page dependency owner if unresolved after 5 minutes."
    ),
    ("cascade", None): (
        "1. Identify blast radius: list all affected services.\n"
        "2. Find the root cause service (highest error rate at t=0).\n"
        "3. Isolate: shed load on the failing dependency.\n"
        "4. Re-enable services one by one after root cause is stable.\n"
        "5. Do NOT restart all services simultaneously — stagger by 30 s."
    ),
    ("error_rate", "P1"): (
        "CRITICAL — FOLLOW THESE STEPS IN ORDER:\n"
        "0. Page on-call lead + incident commander NOW.\n"
        "1. Open incident channel and war-room bridge.\n"
        "2. Identify error class from logs (tail -f / Loki).\n"
        "3. Check recent deploys → rollback immediately if correlated.\n"
        "4. If no deploy: check config changes and feature flags.\n"
        "5. Engage customer success if user impact detected.\n"
        "6. Post a status-page update within 5 minutes of confirmation."
    ),
    ("cascade", "P1"): (
        "CRITICAL — FOLLOW THESE STEPS IN ORDER:\n"
        "0. Page on-call lead + incident commander NOW.\n"
        "1. Open incident channel and war-room bridge.\n"
        "2. Map blast radius — run: python scripts/slo_check.py --output json\n"
        "3. Halt all non-emergency deploys immediately.\n"
        "4. Isolate root-cause service; re-route traffic if possible.\n"
        "5. Recover services bottom-up (dependencies before callers).\n"
        "6. Post status-page update every 10 minutes."
    ),
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class IncidentEvent:
    time_offset_sec: int
    event_type: str
    detail: str


@dataclass
class IncidentScenario:
    scenario_id: str
    fault_type: str
    severity: str
    affected_service: str
    start_time: str          # ISO-8601 UTC
    duration_sec: int
    runbook: str
    timeline: list[IncidentEvent]


# ---------------------------------------------------------------------------
# Scenario generators
# ---------------------------------------------------------------------------

def _generate_latency_spike(
    service: str, severity: str, rng: random.Random
) -> tuple[int, list[IncidentEvent]]:
    """Generate a latency spike timeline."""
    multiplier = {"P1": 20, "P2": 10, "P3": 5, "P4": 2}[severity]
    p99_ms = rng.randint(200, 500) * multiplier
    duration = {"P1": 1800, "P2": 900, "P3": 600, "P4": 300}[severity]

    events = [
        IncidentEvent(0, "anomaly_detected", f"p99 latency rose to {p99_ms} ms on {service}"),
        IncidentEvent(30, "alert_fired", f"SLO latency alert threshold crossed for {service}"),
        IncidentEvent(90, "investigation", "Checking recent deployments and DB slow-query log"),
        IncidentEvent(180, "hypothesis", f"Possible cause: connection pool saturation on {service}"),
        IncidentEvent(duration - 60, "mitigation_started", "Restarting connection pool; scaling read replicas"),
        IncidentEvent(duration, "resolved", f"p99 latency normalized on {service}"),
    ]
    return duration, events


def _generate_error_rate(
    service: str, severity: str, rng: random.Random
) -> tuple[int, list[IncidentEvent]]:
    """Generate an elevated error-rate timeline."""
    error_pct = {"P1": rng.uniform(15, 30), "P2": rng.uniform(5, 15),
                 "P3": rng.uniform(1, 5), "P4": rng.uniform(0.1, 1)}[severity]
    code = rng.choice([500, 502, 503, 504])
    duration = {"P1": 2400, "P2": 1200, "P3": 600, "P4": 300}[severity]

    events = [
        IncidentEvent(0, "anomaly_detected", f"{error_pct:.1f}% {code} errors on {service}"),
        IncidentEvent(15, "alert_fired", f"Error-budget burn-rate alert for {service}"),
        IncidentEvent(60, "investigation", f"Correlating {code} errors with recent deployments"),
        IncidentEvent(120, "hypothesis", "Possible bad deploy or upstream dependency failure"),
        IncidentEvent(duration - 120, "mitigation_started", "Rollback initiated / feature flag disabled"),
        IncidentEvent(duration, "resolved", f"Error rate back below SLO threshold on {service}"),
    ]
    return duration, events


def _generate_dependency_timeout(
    service: str, severity: str, rng: random.Random
) -> tuple[int, list[IncidentEvent]]:
    """Generate a dependency timeout timeline."""
    dep = rng.choice(["postgres-primary", "redis-cache", "payment-gateway", "auth-service"])
    timeout_ms = {"P1": 30000, "P2": 10000, "P3": 5000, "P4": 3000}[severity]
    duration = {"P1": 2100, "P2": 1500, "P3": 900, "P4": 600}[severity]

    events = [
        IncidentEvent(0, "anomaly_detected", f"{dep} not responding (timeout {timeout_ms} ms)"),
        IncidentEvent(20, "alert_fired", f"Dependency health-check failed: {dep}"),
        IncidentEvent(60, "investigation", f"Checking {dep} host status and network path"),
        IncidentEvent(120, "hypothesis", f"{dep} may be overloaded or experiencing a network partition"),
        IncidentEvent(300, "mitigation_started", f"Circuit breaker opened on {service} → {dep}; fallback enabled"),
        IncidentEvent(duration, "resolved", f"{dep} healthy; {service} reconnected"),
    ]
    return duration, events


def _generate_cascade(
    service: str, severity: str, rng: random.Random
) -> tuple[int, list[IncidentEvent]]:
    """Generate a cascade failure timeline."""
    root = service
    downstream = [f"service-{chr(ord('A') + i)}" for i in range(rng.randint(2, 4))]
    duration = {"P1": 3600, "P2": 1800, "P3": 1200, "P4": 600}[severity]
    spread_sec = duration // (len(downstream) + 2)

    events = [IncidentEvent(0, "anomaly_detected", f"Root failure on {root} — errors spreading")]
    for i, svc in enumerate(downstream, start=1):
        events.append(IncidentEvent(
            i * spread_sec,
            "cascade_propagation",
            f"{svc} degraded due to retry storm from {root}",
        ))
    events.append(IncidentEvent(
        len(downstream) * spread_sec + 60,
        "alert_fired",
        f"Multi-service SLO violation: {root} + {len(downstream)} downstream services",
    ))
    events.append(IncidentEvent(
        len(downstream) * spread_sec + 300,
        "mitigation_started",
        f"Load shedding enabled on {root}; downstream retries suppressed",
    ))
    events.append(IncidentEvent(duration, "resolved", "All services recovered; blast radius contained"))
    return duration, events


_GENERATORS = {
    "latency_spike": _generate_latency_spike,
    "error_rate": _generate_error_rate,
    "dependency_timeout": _generate_dependency_timeout,
    "cascade": _generate_cascade,
}


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def _scenario_id(fault_type: str, service: str, seed: int) -> str:
    key = f"{fault_type}:{service}:{seed}".encode()
    digest = int(hashlib.sha256(key).hexdigest(), 16)
    return f"INC-{digest % 100000:05d}"


def generate(
    fault_type: str,
    service: str,
    severity: str | None = None,
    seed: int | None = None,
    reference_time: datetime.datetime | None = None,
) -> IncidentScenario:
    """Generate a deterministic (or random) incident scenario."""
    if fault_type not in FAULT_TYPES:
        raise ValueError(f"unknown fault type '{fault_type}'; choose from: {', '.join(FAULT_TYPES)}")

    resolved_severity = severity or FAULT_DEFAULT_SEVERITY[fault_type]
    if resolved_severity not in SEVERITY_LEVELS:
        raise ValueError(f"unknown severity '{severity}'; choose from: {', '.join(SEVERITY_LEVELS)}")

    effective_seed = seed if seed is not None else random.randint(0, 2**31)
    rng = random.Random(effective_seed)

    ref = reference_time or datetime.datetime.now(datetime.timezone.utc)
    start_iso = ref.strftime("%Y-%m-%dT%H:%M:%SZ")

    duration, events = _GENERATORS[fault_type](service, resolved_severity, rng)

    runbook_key: tuple[str, str | None] = (fault_type, resolved_severity)
    runbook = RUNBOOKS.get(runbook_key) or RUNBOOKS.get((fault_type, None)) or "No runbook available."

    return IncidentScenario(
        scenario_id=_scenario_id(fault_type, service, effective_seed),
        fault_type=fault_type,
        severity=resolved_severity,
        affected_service=service,
        start_time=start_iso,
        duration_sec=duration,
        runbook=runbook,
        timeline=events,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render(scenario: IncidentScenario) -> str:
    lines = [
        f"Incident : {scenario.scenario_id}",
        f"Fault    : {scenario.fault_type}",
        f"Severity : {scenario.severity}",
        f"Service  : {scenario.affected_service}",
        f"Start    : {scenario.start_time}",
        f"Duration : {scenario.duration_sec // 60} min {scenario.duration_sec % 60} sec",
        "",
        "── Timeline ─────────────────────────────────────────────────────────",
    ]
    for ev in sorted(scenario.timeline, key=lambda e: e.time_offset_sec):
        ts = f"T+{ev.time_offset_sec // 60:02d}:{ev.time_offset_sec % 60:02d}"
        lines.append(f"  {ts}  [{ev.event_type:25s}]  {ev.detail}")

    lines += [
        "",
        "── Runbook ──────────────────────────────────────────────────────────",
    ]
    for line in scenario.runbook.splitlines():
        lines.append(f"  {line}")
    lines.append("")
    return "\n".join(lines)


def to_json(scenario: IncidentScenario) -> str:
    return json.dumps(asdict(scenario), indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate SRE incident scenarios for testing runbooks and triage tooling."
    )
    parser.add_argument(
        "--fault-type", "-f",
        choices=FAULT_TYPES,
        default="error_rate",
        help="type of fault to simulate (default: error_rate)",
    )
    parser.add_argument(
        "--service", "-s",
        default="payments-api",
        help="name of the affected service (default: payments-api)",
    )
    parser.add_argument(
        "--severity",
        choices=SEVERITY_LEVELS,
        default=None,
        help="incident severity; auto-derived from fault type when omitted",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="random seed for deterministic output",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "--list-runbooks",
        action="store_true",
        help="print all available runbook keys and exit",
    )
    args = parser.parse_args()

    if args.list_runbooks:
        print("Available runbook keys (fault_type, severity):")
        for (ft, sv) in sorted(RUNBOOKS.keys(), key=lambda k: (k[0], k[1] or "")):
            label = f"{ft} / {sv or 'default'}"
            print(f"  {label}")
        return 0

    try:
        scenario = generate(
            fault_type=args.fault_type,
            service=args.service,
            severity=args.severity,
            seed=args.seed,
        )
    except ValueError as exc:
        print(f"incident-sim: {exc}", file=sys.stderr)
        return 2

    if args.output == "json":
        print(to_json(scenario))
    else:
        print(render(scenario))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
