#!/usr/bin/env python3
"""Fail on high/critical npm findings except narrow, current risk acceptances."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
ALLOWLIST = ROOT / "security/npm-audit-allowlist.json"


def advisory_ids(vulnerability: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for item in vulnerability.get("via", []):
        if isinstance(item, dict) and "/advisories/" in item.get("url", ""):
            values.add(item["url"].rsplit("/", 1)[-1])
    return values


def evaluate(audit: dict[str, Any], allowlist: dict[str, Any], today: dt.date) -> tuple[list[str], list[str]]:
    accepted: list[str] = []
    failures: list[str] = []
    accepted_packages: set[str] = set()
    aggregates: list[tuple[str, dict[str, Any]]] = []
    exceptions = {item["package"]: item for item in allowlist.get("exceptions", [])}
    for package, finding in audit.get("vulnerabilities", {}).items():
        if finding.get("severity") not in {"high", "critical"}:
            continue
        exception = exceptions.get(package)
        actual = advisory_ids(finding)
        if not actual and all(isinstance(item, str) for item in finding.get("via", [])):
            aggregates.append((package, finding))
            continue
        if not exception:
            failures.append(f"{package}: unapproved {finding['severity']} finding(s) {sorted(actual)}")
            continue
        expiry = dt.date.fromisoformat(exception["expires"])
        expected = set(exception["advisories"])
        if today > expiry:
            failures.append(f"{package}: risk acceptance expired {expiry}")
        elif finding.get("isDirect", True):
            failures.append(f"{package}: exception is only valid for a transitive dependency")
        elif actual != expected:
            failures.append(f"{package}: advisory set changed; expected {sorted(expected)}, got {sorted(actual)}")
        else:
            accepted.append(f"{package}: {sorted(actual)} accepted until {expiry} by {exception['owner']}")
            accepted_packages.add(package)
    for package, finding in aggregates:
        dependencies = set(finding.get("via", []))
        if dependencies and dependencies <= accepted_packages:
            accepted.append(f"{package}: aggregate finding inherited only from accepted {sorted(dependencies)}")
        else:
            failures.append(f"{package}: unapproved aggregate finding via {sorted(dependencies)}")
    return accepted, failures


def main() -> int:
    audit_process = subprocess.run(["npm", "audit", "--json"], cwd=WEB, text=True, capture_output=True)
    try:
        audit = json.loads(audit_process.stdout)
        allowlist = json.loads(ALLOWLIST.read_text())
    except json.JSONDecodeError as exc:
        print(f"FAIL npm audit output: {exc}", file=sys.stderr)
        return 1
    accepted, failures = evaluate(audit, allowlist, dt.datetime.now(dt.timezone.utc).date())

    production_tree = subprocess.run(
        ["npm", "ls", "--omit=dev", "image-size"], cwd=WEB, text=True, capture_output=True
    )
    if production_tree.returncode == 0 and "image-size@" in production_tree.stdout:
        failures.append("image-size entered the production dependency tree")
    for item in accepted:
        print(f"ACCEPTED {item}")
    if failures:
        for item in failures:
            print(f"FAIL {item}", file=sys.stderr)
        return 1
    print("PASS no unapproved high or critical npm findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
