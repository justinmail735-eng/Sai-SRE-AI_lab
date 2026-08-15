#!/usr/bin/env python3
"""Reject first-party GitHub Actions that still use the retired Node 20 runtime."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
MINIMUM_MAJORS = {"checkout": 5, "setup-node": 5}
ACTION_PATTERN = re.compile(r"actions/(checkout|setup-node)@v(\d+)")


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


def main() -> int:
    findings = outdated_actions(WORKFLOWS)
    if findings:
        print("FAIL workflow-runtime-hygiene")
        print("\n".join(findings))
        return 1
    print("PASS workflow-runtime-hygiene")
    return 0


if __name__ == "__main__":
    sys.exit(main())
