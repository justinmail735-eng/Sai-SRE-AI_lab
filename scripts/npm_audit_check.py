#!/usr/bin/env python3
"""Fail on high/critical npm findings except narrow, current risk acceptances."""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
ALLOWLIST = ROOT / "security/npm-audit-allowlist.json"
ALLOWLIST_FIELDS = {"package", "advisories", "owner", "expires", "scope", "rationale"}
DEV_ONLY_SCOPE = "transitive development dependencies only"


def advisory_ids(vulnerability: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for item in vulnerability.get("via", []):
        if isinstance(item, dict) and "/advisories/" in item.get("url", ""):
            values.add(item["url"].rsplit("/", 1)[-1])
    return values


def validate_allowlist(allowlist: dict[str, Any]) -> list[str]:
    """Validate the complete risk-acceptance contract before using any exception."""
    if not isinstance(allowlist, dict) or set(allowlist) != {"api_version", "exceptions"}:
        return ["npm audit allowlist must contain exactly api_version and exceptions"]
    if allowlist.get("api_version") != "sentinelsre.io/v1":
        return ["npm audit allowlist has an unsupported api_version"]
    exceptions = allowlist.get("exceptions")
    if not isinstance(exceptions, list):
        return ["npm audit allowlist exceptions must be an array"]

    failures: list[str] = []
    packages: set[str] = set()
    for index, exception in enumerate(exceptions, start=1):
        label = f"npm audit exception {index}"
        if not isinstance(exception, dict) or set(exception) != ALLOWLIST_FIELDS:
            failures.append(f"{label} must contain exactly {sorted(ALLOWLIST_FIELDS)}")
            continue
        package = exception["package"]
        if not isinstance(package, str) or not package.strip():
            failures.append(f"{label} package must be a non-empty string")
        elif package in packages:
            failures.append(f"{label} duplicates package '{package}'")
        else:
            packages.add(package)
        advisories = exception["advisories"]
        if (
            not isinstance(advisories, list)
            or not advisories
            or any(
                not isinstance(item, str)
                or not re.fullmatch(r"GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}", item)
                for item in advisories
            )
            or len(advisories) != len(set(advisories))
        ):
            failures.append(f"{label} advisories must be unique GHSA identifiers")
        for field in ("owner", "rationale"):
            if not isinstance(exception[field], str) or not exception[field].strip():
                failures.append(f"{label} {field} must be a non-empty string")
        if exception["scope"] != DEV_ONLY_SCOPE:
            failures.append(f"{label} scope must be '{DEV_ONLY_SCOPE}'")
        try:
            dt.date.fromisoformat(exception["expires"])
        except (TypeError, ValueError):
            failures.append(f"{label} expires must be an ISO date")
    return failures


def evaluate(audit: dict[str, Any], allowlist: dict[str, Any], today: dt.date) -> tuple[list[str], list[str]]:
    accepted: list[str] = []
    failures = validate_allowlist(allowlist)
    if failures:
        return accepted, failures
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
    pending = aggregates
    while pending:
        unresolved: list[tuple[str, dict[str, Any]]] = []
        for package, finding in pending:
            dependencies = set(finding.get("via", []))
            if dependencies and dependencies <= accepted_packages:
                accepted.append(
                    f"{package}: aggregate finding inherited only from accepted {sorted(dependencies)}"
                )
                accepted_packages.add(package)
            else:
                unresolved.append((package, finding))
        if len(unresolved) == len(pending):
            for package, finding in unresolved:
                dependencies = set(finding.get("via", []))
                failures.append(
                    f"{package}: unapproved aggregate finding via {sorted(dependencies)}"
                )
            break
        pending = unresolved
    return accepted, failures


def production_exception_failures(
    lockfile: dict[str, Any], allowlist: dict[str, Any]
) -> list[str]:
    """Reject risk-accepted packages on any production dependency path."""
    packages = lockfile.get("packages")
    if not isinstance(packages, dict):
        return ["package lock has no packages map; production dependency scope is unverifiable"]
    exceptions = {
        item.get("package") for item in allowlist.get("exceptions", []) if isinstance(item, dict)
    }
    failures: list[str] = []
    for package in sorted(name for name in exceptions if isinstance(name, str)):
        suffix = f"node_modules/{package}"
        production_paths = sorted(
            path for path, metadata in packages.items()
            if (path == suffix or path.endswith(f"/{suffix}"))
            and (not isinstance(metadata, dict) or metadata.get("dev") is not True)
        )
        if production_paths:
            failures.append(
                f"{package}: risk-accepted package entered production dependency path(s) "
                f"{production_paths}"
            )
    return failures


def main() -> int:
    audit_process = subprocess.run(["npm", "audit", "--json"], cwd=WEB, text=True, capture_output=True)
    try:
        audit = json.loads(audit_process.stdout)
        allowlist = json.loads(ALLOWLIST.read_text())
        lockfile = json.loads((WEB / "package-lock.json").read_text())
    except json.JSONDecodeError as exc:
        print(f"FAIL npm security input: {exc}", file=sys.stderr)
        return 1
    accepted, failures = evaluate(audit, allowlist, dt.datetime.now(dt.timezone.utc).date())
    failures.extend(production_exception_failures(lockfile, allowlist))
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
