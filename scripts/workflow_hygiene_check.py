#!/usr/bin/env python3
"""Enforce immutable GitHub Action dependencies and supported first-party runtimes."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
MINIMUM_MAJORS = {"checkout": 5, "setup-node": 5}
ACTION_PATTERN = re.compile(r"actions/(checkout|setup-node)@v(\d+)")
USE_PATTERN = re.compile(r"^\s*-\s+uses:\s+([^\s@]+)@([^\s#]+)")
COMMIT_SHA = re.compile(r"[0-9a-f]{40}")


def outdated_actions(workflows: Path) -> list[str]:
    findings: list[str] = []
    for workflow in sorted(workflows.glob("*.y*ml")):
        for line_number, line in enumerate(workflow.read_text().splitlines(), start=1):
            for action, major_text in ACTION_PATTERN.findall(line):
                major = int(major_text)
                if major < MINIMUM_MAJORS[action]:
                    findings.append(
                        f"{workflow.relative_to(workflows.parent.parent)}:{line_number}: "
                        f"actions/{action}@v{major} must be v{MINIMUM_MAJORS[action]} or newer"
                    )
    return findings


def unpinned_actions(workflows: Path) -> list[str]:
    findings: list[str] = []
    for workflow in sorted(workflows.glob("*.y*ml")):
        for line_number, line in enumerate(workflow.read_text().splitlines(), start=1):
            match = USE_PATTERN.match(line)
            if match and not match.group(1).startswith("./") and not COMMIT_SHA.fullmatch(match.group(2)):
                findings.append(
                    f"{workflow.relative_to(workflows.parent.parent)}:{line_number}: "
                    f"{match.group(1)}@{match.group(2)} must use an immutable 40-character commit SHA"
                )
    return findings


def main() -> int:
    findings = outdated_actions(WORKFLOWS) + unpinned_actions(WORKFLOWS)
    if findings:
        print("FAIL workflow-supply-chain-hygiene")
        print("\n".join(findings))
        return 1
    print("PASS workflow-supply-chain-hygiene")
    return 0


if __name__ == "__main__":
    sys.exit(main())
