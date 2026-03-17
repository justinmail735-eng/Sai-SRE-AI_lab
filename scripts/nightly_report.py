#!/usr/bin/env python3
"""Nightly SLO health report aggregator.

Reads an SLO policy file, evaluates all services via the slo_check engine,
and emits a structured report (text, JSON, or markdown) suitable for daily
review or automated alerting pipelines.

Exit codes:
  0 — all services passing
  1 — one or more services in critical (or warning if --fail-on-warning)
  2 — invalid policy or tool failure
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path
from typing import List

# Allow importing slo_check from the same scripts/ directory without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from slo_check import ServiceResult, WindowResult, evaluate  # noqa: E402


_STATE_ICON = {
    "pass": "OK",
    "warning": "WARN",
    "critical": "CRIT",
    "insufficient-data": "NODATA",
}


def _worst_window(service: ServiceResult) -> WindowResult | None:
    """Return the window with the highest-severity state, breaking ties by burn rate."""
    priority = {"critical": 0, "warning": 1, "insufficient-data": 2, "pass": 3}
    return min(
        service.windows,
        key=lambda w: (priority.get(w.state, 9), -w.burn_rate),
        default=None,
    )


def _burn_str(burn_rate: float) -> str:
    return "inf" if math.isinf(burn_rate) else f"{burn_rate:.2f}x"


def _render_text(results: List[ServiceResult], generated_at: datetime.datetime) -> str:
    ts = generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        f"Nightly SLO Report — {ts}",
        "=" * 64,
        "",
    ]

    for svc in results:
        tag = _STATE_ICON.get(svc.state, "?")
        lines.append(f"  [{tag}] {svc.name} ({svc.state.upper()})")
        lines.append(f"    Owner  : {svc.owner or 'unknown'}")
        lines.append(f"    Target : {svc.target * 100:.3f}%  budget={svc.budget * 100:.4f}%")
        for w in svc.windows:
            lines.append(
                f"      [{w.state:>17}] {w.label:>4} ({w.minutes}m)  "
                f"burn={_burn_str(w.burn_rate):>6}  "
                f"avail={w.availability * 100:.4f}%  "
                f"budget_remaining={w.budget_requests_remaining} req"
            )
        lines.append("")

    counts: dict[str, int] = {}
    for r in results:
        counts[r.state] = counts.get(r.state, 0) + 1
    summary_parts = [f"{v} {k}" for k, v in sorted(counts.items())]
    lines.append(f"SUMMARY: {len(results)} service(s) — {', '.join(summary_parts)}")

    alerts = [r for r in results if r.state in ("critical", "warning")]
    if alerts:
        lines += ["", "ALERTS:"]
        for svc in alerts:
            worst = _worst_window(svc)
            worst_desc = ""
            if worst:
                worst_desc = f" — worst window: {worst.label} ({_burn_str(worst.burn_rate)} burn)"
            tag = _STATE_ICON.get(svc.state, "?")
            lines.append(f"  [{tag}] {svc.name}{worst_desc}")

    return "\n".join(lines)


def _render_markdown(results: List[ServiceResult], generated_at: datetime.datetime) -> str:
    ts = generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "# Nightly SLO Report",
        "",
        f"Generated: {ts}",
        "",
        "## Service Status",
        "",
        "| Service | Owner | Target | State | Worst Window | Burn Rate |",
        "|---------|-------|--------|-------|--------------|-----------|",
    ]

    for svc in results:
        worst = _worst_window(svc)
        worst_label = worst.label if worst else ""
        worst_burn = _burn_str(worst.burn_rate) if worst else ""
        owner = (svc.owner or "unknown").replace("|", "\\|")
        lines.append(
            f"| {svc.name} | {owner} | {svc.target * 100:.3f}% | "
            f"{svc.state} | {worst_label} | {worst_burn} |"
        )

    counts: dict[str, int] = {}
    for r in results:
        counts[r.state] = counts.get(r.state, 0) + 1

    lines += ["", "## Summary", ""]
    for state, count in sorted(counts.items()):
        lines.append(f"- **{state}**: {count}")

    alerts = [r for r in results if r.state in ("critical", "warning")]
    if alerts:
        lines += ["", "## Alerts", ""]
        for svc in alerts:
            worst = _worst_window(svc)
            if worst:
                lines.append(
                    f"- **{svc.state.upper()}** `{svc.name}` — "
                    f"window `{worst.label}` burning at {_burn_str(worst.burn_rate)}"
                )
            else:
                lines.append(f"- **{svc.state.upper()}** `{svc.name}`")

    return "\n".join(lines)


def _render_json(results: List[ServiceResult], generated_at: datetime.datetime) -> str:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.state] = counts.get(r.state, 0) + 1
    return json.dumps(
        {
            "generated_at": generated_at.isoformat(),
            "services": [asdict(r) for r in results],
            "summary": counts,
        },
        indent=2,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a nightly SLO health report from a policy file."
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=Path("projects/01-slo-engine/sample-slo.json"),
        help="path to SLO policy JSON (default: projects/01-slo-engine/sample-slo.json)",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json", "markdown"),
        default="text",
        help="output format: text (default), json, or markdown",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="exit 1 if any service is in WARNING state",
    )
    parser.add_argument(
        "--require-owner",
        action="store_true",
        help="fail if any service omits a non-empty owner field",
    )
    parser.add_argument(
        "--fail-on-insufficient-data",
        action="store_true",
        help="exit 1 if any evaluated window is marked insufficient-data",
    )
    args = parser.parse_args()

    try:
        data = json.loads(args.input.read_text())
        results = evaluate(data, require_owner=args.require_owner)
    except Exception as exc:
        print(f"nightly-report: failed to evaluate policy: {exc}", file=sys.stderr)
        return 2

    generated_at = datetime.datetime.utcnow()

    if args.output == "json":
        print(_render_json(results, generated_at))
    elif args.output == "markdown":
        print(_render_markdown(results, generated_at))
    else:
        print(_render_text(results, generated_at))

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
