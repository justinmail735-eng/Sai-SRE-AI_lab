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
import csv
import datetime
import io
import json
import math
import re
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


def _build_owner_summary(results: List[ServiceResult]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for svc in results:
        owner = (svc.owner or "unknown").strip() or "unknown"
        owner_bucket = summary.setdefault(
            owner,
            {"total": 0, "critical": 0, "warning": 0, "insufficient-data": 0, "pass": 0},
        )
        owner_bucket["total"] += 1
        owner_bucket[svc.state] = owner_bucket.get(svc.state, 0) + 1
    return summary


def _worst_window(service: ServiceResult) -> WindowResult | None:
    """Return the window with the highest-severity state, breaking ties by burn rate."""
    priority = {"critical": 0, "warning": 1, "insufficient-data": 2, "pass": 3}
    return min(
        service.windows,
        key=lambda w: (priority.get(w.state, 9), -w.burn_rate),
        default=None,
    )


def _service_sort_key(service: ServiceResult) -> tuple[int, float, str]:
    """Sort by severity, then worst-window burn-rate descending, then name."""
    priority = {"critical": 0, "warning": 1, "insufficient-data": 2, "pass": 3}
    worst = _worst_window(service)
    burn = worst.burn_rate if worst else 0.0
    return (priority.get(service.state, 9), -burn, service.name)


def _burn_str(burn_rate: float) -> str:
    return "inf" if math.isinf(burn_rate) else f"{burn_rate:.2f}x"


def _render_text(
    results: List[ServiceResult],
    generated_at: datetime.datetime,
    summary_only: bool = False,
    owner_summary: bool = False,
    max_alerts: int | None = None,
) -> str:
    ts = generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        f"Nightly SLO Report — {ts}",
        "=" * 64,
        "",
    ]

    if not summary_only:
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

    if owner_summary:
        owner_counts = _build_owner_summary(results)
        lines += ["", "OWNER SUMMARY:"]
        for owner in sorted(owner_counts):
            counts = owner_counts[owner]
            lines.append(
                "  "
                f"- {owner}: total={counts['total']}, critical={counts['critical']}, "
                f"warning={counts['warning']}, insufficient-data={counts['insufficient-data']}, pass={counts['pass']}"
            )

    alerts = [r for r in results if r.state in ("critical", "warning")]
    truncated_alerts = False
    if max_alerts is not None and len(alerts) > max_alerts:
        alerts = alerts[:max_alerts]
        truncated_alerts = True
    if alerts:
        lines += ["", "ALERTS:"]
        for svc in alerts:
            worst = _worst_window(svc)
            worst_desc = ""
            if worst:
                worst_desc = f" — worst window: {worst.label} ({_burn_str(worst.burn_rate)} burn)"
            tag = _STATE_ICON.get(svc.state, "?")
            lines.append(f"  [{tag}] {svc.name}{worst_desc}")
        if truncated_alerts:
            lines.append(f"  ... truncated to top {max_alerts} alert(s)")

    return "\n".join(lines)


def _render_markdown(
    results: List[ServiceResult],
    generated_at: datetime.datetime,
    summary_only: bool = False,
    owner_summary: bool = False,
    max_alerts: int | None = None,
) -> str:
    ts = generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "# Nightly SLO Report",
        "",
        f"Generated: {ts}",
    ]

    if not summary_only:
        lines += [
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

    if owner_summary:
        owner_counts = _build_owner_summary(results)
        lines += ["", "## Owner Summary", ""]
        lines += [
            "| Owner | Total | Critical | Warning | Insufficient Data | Pass |",
            "|-------|-------|----------|---------|-------------------|------|",
        ]
        for owner in sorted(owner_counts):
            counts = owner_counts[owner]
            safe_owner = owner.replace("|", "\\|")
            lines.append(
                f"| {safe_owner} | {counts['total']} | {counts['critical']} | {counts['warning']} | "
                f"{counts['insufficient-data']} | {counts['pass']} |"
            )

    alerts = [r for r in results if r.state in ("critical", "warning")]
    truncated_alerts = False
    if max_alerts is not None and len(alerts) > max_alerts:
        alerts = alerts[:max_alerts]
        truncated_alerts = True
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
        if truncated_alerts:
            lines.append("")
            lines.append(f"_Truncated to top {max_alerts} alert(s)._")

    return "\n".join(lines)


def _render_csv(
    results: List[ServiceResult],
    generated_at: datetime.datetime,
    summary_only: bool = False,
    max_alerts: int | None = None,
) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    if summary_only:
        writer.writerow(["generated_at", generated_at.isoformat()])
        writer.writerow([])
        writer.writerow(["service", "state", "owner", "worst_window", "worst_burn_rate"])
        alerts = [svc for svc in results if svc.state in ("warning", "critical")]
        if max_alerts is not None:
            alerts = alerts[:max_alerts]
        for svc in alerts:
            worst = _worst_window(svc)
            writer.writerow(
                [
                    svc.name,
                    svc.state,
                    svc.owner or "",
                    worst.label if worst else "",
                    worst.burn_rate if worst else "",
                ]
            )
    else:
        writer.writerow(
            [
                "service",
                "owner",
                "target",
                "state",
                "window",
                "window_minutes",
                "availability",
                "burn_rate",
                "budget_requests_remaining",
            ]
        )
        for svc in results:
            for w in svc.windows:
                writer.writerow(
                    [
                        svc.name,
                        svc.owner or "",
                        f"{svc.target:.6f}",
                        svc.state,
                        w.label,
                        w.minutes,
                        f"{w.availability:.6f}",
                        w.burn_rate,
                        w.budget_requests_remaining,
                    ]
                )

    return buffer.getvalue().rstrip("\n")


def _render_json(
    results: List[ServiceResult],
    generated_at: datetime.datetime,
    summary_only: bool = False,
    owner_summary: bool = False,
    max_alerts: int | None = None,
) -> str:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.state] = counts.get(r.state, 0) + 1
    payload = {
        "generated_at": generated_at.isoformat(),
        "summary": counts,
    }
    if owner_summary:
        payload["owner_summary"] = _build_owner_summary(results)

    if summary_only:
        alerts = [
            {
                "name": svc.name,
                "state": svc.state,
                "owner": svc.owner,
                "worst_window": (
                    {
                        "label": worst.label,
                        "burn_rate": worst.burn_rate,
                        "window_minutes": worst.minutes,
                    }
                    if (worst := _worst_window(svc))
                    else None
                ),
            }
            for svc in results
            if svc.state in ("critical", "warning")
        ]
        if max_alerts is not None:
            alerts = alerts[:max_alerts]
        payload["alerts"] = alerts
    else:
        payload["services"] = [asdict(r) for r in results]

    return json.dumps(payload, indent=2)


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
        choices=("text", "json", "markdown", "csv"),
        default="text",
        help="output format: text (default), json, markdown, or csv",
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
    parser.add_argument(
        "--service-regex",
        default=None,
        help="optional regex to evaluate and render only matching services by name",
    )
    parser.add_argument(
        "--owner-regex",
        default=None,
        help="optional regex to include only services whose owner matches (owner is treated as empty when missing)",
    )
    parser.add_argument(
        "--only-state",
        default=None,
        help="optional comma-separated service states to include (pass, warning, critical, insufficient-data)",
    )
    parser.add_argument(
        "--sort",
        choices=("severity", "name"),
        default="severity",
        help="service ordering for report output: severity (default) or name",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="optional max number of services to include after filtering/sorting",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="emit compact output with summary (+ alerts) and omit per-service detail",
    )
    parser.add_argument(
        "--owner-summary",
        action="store_true",
        help="include owner-level state totals in report output (text/markdown/json)",
    )
    parser.add_argument(
        "--alerts-only",
        action="store_true",
        help="include only services in warning/critical state",
    )
    parser.add_argument(
        "--min-burn-rate",
        type=float,
        default=None,
        help="optional filter to include only services whose worst-window burn rate is >= this value",
    )
    parser.add_argument(
        "--max-alerts",
        type=int,
        default=None,
        help="optional cap on alert entries rendered in alerts sections/summary outputs",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="optional path to write rendered report output (stdout is still emitted unless --no-stdout)",
    )
    parser.add_argument(
        "--no-stdout",
        action="store_true",
        help="suppress stdout output (requires --output-file)",
    )
    parser.add_argument(
        "--generated-at",
        default=None,
        help="optional ISO-8601 UTC timestamp to stamp the report (for deterministic replays/backfills)",
    )
    args = parser.parse_args()

    if args.no_stdout and args.output_file is None:
        print("nightly-report: --no-stdout requires --output-file", file=sys.stderr)
        return 2

    try:
        data = json.loads(args.input.read_text())
        results = evaluate(data, require_owner=args.require_owner)
    except Exception as exc:
        print(f"nightly-report: failed to evaluate policy: {exc}", file=sys.stderr)
        return 2

    if args.service_regex:
        try:
            service_pattern = re.compile(args.service_regex)
        except re.error as exc:
            print(f"nightly-report: invalid --service-regex pattern: {exc}", file=sys.stderr)
            return 2

        filtered = [svc for svc in results if service_pattern.search(svc.name)]
        if not filtered:
            print(
                f"nightly-report: --service-regex '{args.service_regex}' matched no services",
                file=sys.stderr,
            )
            return 2
        results = filtered

    if args.owner_regex:
        try:
            owner_pattern = re.compile(args.owner_regex)
        except re.error as exc:
            print(f"nightly-report: invalid --owner-regex pattern: {exc}", file=sys.stderr)
            return 2

        filtered = [svc for svc in results if owner_pattern.search(svc.owner or "")]
        if not filtered:
            print(
                f"nightly-report: --owner-regex '{args.owner_regex}' matched no services",
                file=sys.stderr,
            )
            return 2
        results = filtered

    if args.only_state:
        valid_states = {"pass", "warning", "critical", "insufficient-data"}
        requested_states = {state.strip().lower() for state in args.only_state.split(",") if state.strip()}
        invalid_states = sorted(requested_states - valid_states)
        if invalid_states:
            print(
                "nightly-report: invalid --only-state value(s): " + ", ".join(invalid_states),
                file=sys.stderr,
            )
            return 2
        if not requested_states:
            print("nightly-report: --only-state requires at least one state", file=sys.stderr)
            return 2

        filtered_by_state = [svc for svc in results if svc.state in requested_states]
        if not filtered_by_state:
            print(
                f"nightly-report: --only-state '{args.only_state}' matched no services",
                file=sys.stderr,
            )
            return 2
        results = filtered_by_state

    if args.alerts_only:
        filtered_alerts = [svc for svc in results if svc.state in {"warning", "critical"}]
        if not filtered_alerts:
            print("nightly-report: --alerts-only matched no services", file=sys.stderr)
            return 2
        results = filtered_alerts

    if args.min_burn_rate is not None:
        if args.min_burn_rate < 0:
            print("nightly-report: --min-burn-rate must be >= 0", file=sys.stderr)
            return 2

        filtered_by_burn = [
            svc for svc in results
            if (worst := _worst_window(svc)) is not None and worst.burn_rate >= args.min_burn_rate
        ]
        if not filtered_by_burn:
            print(
                f"nightly-report: --min-burn-rate '{args.min_burn_rate}' matched no services",
                file=sys.stderr,
            )
            return 2
        results = filtered_by_burn

    if args.max_alerts is not None and args.max_alerts < 1:
        print("nightly-report: --max-alerts must be >= 1", file=sys.stderr)
        return 2

    if args.sort == "name":
        results = sorted(results, key=lambda svc: svc.name)
    else:
        results = sorted(results, key=_service_sort_key)

    if args.limit is not None:
        if args.limit < 1:
            print("nightly-report: --limit must be >= 1", file=sys.stderr)
            return 2
        results = results[: args.limit]
        if not results:
            print("nightly-report: --limit excluded all services", file=sys.stderr)
            return 2

    if args.generated_at:
        normalized = args.generated_at.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed_generated_at = datetime.datetime.fromisoformat(normalized)
        except ValueError:
            print(
                "nightly-report: --generated-at must be ISO-8601 (example: 2026-03-16T06:01:00Z)",
                file=sys.stderr,
            )
            return 2

        if parsed_generated_at.tzinfo is None:
            generated_at = parsed_generated_at.replace(tzinfo=datetime.timezone.utc)
        else:
            generated_at = parsed_generated_at.astimezone(datetime.timezone.utc)
    else:
        generated_at = datetime.datetime.now(datetime.timezone.utc)

    if args.output == "json":
        rendered_output = _render_json(
            results,
            generated_at,
            summary_only=args.summary_only,
            owner_summary=args.owner_summary,
            max_alerts=args.max_alerts,
        )
    elif args.output == "markdown":
        rendered_output = _render_markdown(
            results,
            generated_at,
            summary_only=args.summary_only,
            owner_summary=args.owner_summary,
            max_alerts=args.max_alerts,
        )
    elif args.output == "csv":
        rendered_output = _render_csv(
            results,
            generated_at,
            summary_only=args.summary_only,
            max_alerts=args.max_alerts,
        )
    else:
        rendered_output = _render_text(
            results,
            generated_at,
            summary_only=args.summary_only,
            owner_summary=args.owner_summary,
            max_alerts=args.max_alerts,
        )

    if args.output_file is not None:
        try:
            args.output_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_output = args.output_file.with_suffix(args.output_file.suffix + ".tmp")
            tmp_output.write_text(rendered_output + "\n")
            tmp_output.replace(args.output_file)
        except OSError as exc:
            print(f"nightly-report: failed to write --output-file: {exc}", file=sys.stderr)
            return 2

    if not args.no_stdout:
        print(rendered_output)

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
