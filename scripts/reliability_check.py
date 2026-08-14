#!/usr/bin/env python3
"""Continuously validate agent-generated reliability artifacts and SLO policy."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "reliability" / "services"
GENERATED = ROOT / "observability" / "generated"
AGENT = ROOT / "agents" / "observability_agent.py"
SLO_CHECK = ROOT / "scripts" / "slo_check.py"
DEFAULT_SLO = ROOT / "reliability" / "telemetry" / "healthy-snapshot.json"


def check_command(label: str, command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    return {
        "name": label,
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def run_checks(slo_input: Path) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    service_specs = sorted(SERVICES.glob("*.json"))
    if not service_specs:
        return [{"name": "service-discovery", "passed": False, "returncode": 2, "stdout": "", "stderr": "no service specifications found"}]

    for service_spec in service_specs:
        output_dir = GENERATED / service_spec.stem
        checks.append(
            check_command(
                f"observability-drift:{service_spec.stem}",
                [
                    sys.executable,
                    str(AGENT),
                    "--spec",
                    str(service_spec),
                    "--output-dir",
                    str(output_dir),
                    "--check",
                ],
            )
        )

    checks.append(
        check_command(
            "slo-policy",
            [
                sys.executable,
                str(SLO_CHECK),
                "--input",
                str(slo_input),
                "--require-owner",
                "--fail-on-warning",
                "--fail-on-insufficient-data",
            ],
        )
    )
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slo-input", type=Path, default=DEFAULT_SLO)
    parser.add_argument("--output", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    checks = run_checks(args.slo_input)
    passed = all(bool(check["passed"]) for check in checks)
    if args.output == "json":
        print(json.dumps({"passed": passed, "checks": checks}, indent=2, sort_keys=True))
    else:
        for check in checks:
            print(f"{'PASS' if check['passed'] else 'FAIL'} {check['name']}")
            if not check["passed"]:
                details = check["stderr"] or check["stdout"]
                if details:
                    print(f"  {details}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
