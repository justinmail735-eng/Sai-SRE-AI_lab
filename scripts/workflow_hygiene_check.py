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
USE_PATTERN = re.compile(r"^\s*(?:-\s+)?uses:\s+([^\s@]+)@([^\s#]+)")
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


def checkouts_with_persisted_credentials(workflows: Path) -> list[str]:
    findings: list[str] = []
    for workflow in sorted(workflows.glob("*.y*ml")):
        lines = workflow.read_text().splitlines()
        for index, line in enumerate(lines):
            if "uses: actions/checkout@" not in line:
                continue
            step_indent = len(line) - len(line.lstrip())
            end = index + 1
            while end < len(lines):
                candidate = lines[end]
                candidate_indent = len(candidate) - len(candidate.lstrip())
                if candidate.strip().startswith("- ") and candidate_indent <= step_indent:
                    break
                end += 1
            if not any(re.fullmatch(r"\s+persist-credentials:\s+false", item) for item in lines[index:end]):
                findings.append(
                    f"{workflow.relative_to(workflows.parent.parent)}:{index + 1}: "
                    "actions/checkout must set persist-credentials: false"
                )
    return findings


def workflows_without_concurrency(workflows: Path) -> list[str]:
    findings: list[str] = []
    for workflow in sorted(workflows.glob("*.y*ml")):
        lines = workflow.read_text().splitlines()
        jobs_start = next((index for index, line in enumerate(lines) if line == "jobs:"), len(lines))
        preamble = lines[:jobs_start]
        concurrency_start = next(
            (index for index, line in enumerate(preamble) if line == "concurrency:"),
            None,
        )
        valid = False
        if concurrency_start is not None:
            block = preamble[concurrency_start + 1:]
            valid = (
                any(re.fullmatch(r"  group:\s+.+", line) for line in block)
                and any(re.fullmatch(r"  cancel-in-progress:\s+.+", line) for line in block)
            )
        if not valid:
            findings.append(
                f"{workflow.relative_to(workflows.parent.parent)}: workflow must define "
                "a concurrency group and cancel-in-progress policy"
            )
    return findings


def security_workflows_without_schedule(workflows: Path) -> list[str]:
    findings: list[str] = []
    for workflow in sorted(workflows.glob("*supply-chain*.y*ml")):
        lines = workflow.read_text().splitlines()
        jobs_start = next((index for index, line in enumerate(lines) if line == "jobs:"), len(lines))
        preamble = lines[:jobs_start]
        schedule_start = next(
            (index for index, line in enumerate(preamble) if re.fullmatch(r"  schedule:", line)),
            None,
        )
        scheduled = schedule_start is not None and any(
            re.fullmatch(r'    - cron:\s+"[^\"]+"', line)
            for line in preamble[schedule_start + 1:]
        )
        if not scheduled:
            findings.append(
                f"{workflow.relative_to(workflows.parent.parent)}: supply-chain workflow "
                "must define a recurring cron scan"
            )
    return findings


def jobs_without_timeouts(workflows: Path) -> list[str]:
    findings: list[str] = []
    for workflow in sorted(workflows.glob("*.y*ml")):
        lines = workflow.read_text().splitlines()
        jobs_start = next((index for index, line in enumerate(lines) if line == "jobs:"), None)
        if jobs_start is None:
            continue
        job_starts = [
            index for index in range(jobs_start + 1, len(lines))
            if re.fullmatch(r"  [A-Za-z0-9_-]+:", lines[index])
        ]
        for position, start in enumerate(job_starts):
            end = job_starts[position + 1] if position + 1 < len(job_starts) else len(lines)
            job_name = lines[start].strip()[:-1]
            if not any(re.fullmatch(r"    timeout-minutes:\s+[1-9][0-9]*", line) for line in lines[start:end]):
                findings.append(
                    f"{workflow.relative_to(workflows.parent.parent)}:{start + 1}: "
                    f"job {job_name} must define a positive timeout-minutes budget"
                )
    return findings


def jobs_with_mutable_runner_labels(workflows: Path) -> list[str]:
    findings: list[str] = []
    for workflow in sorted(workflows.glob("*.y*ml")):
        for line_number, line in enumerate(workflow.read_text().splitlines(), start=1):
            match = re.fullmatch(r"\s+runs-on:\s+([^\s#]+)", line)
            if match and match.group(1).endswith("-latest"):
                findings.append(
                    f"{workflow.relative_to(workflows.parent.parent)}:{line_number}: "
                    f"runner label {match.group(1)} must pin an explicit OS version"
                )
    return findings


def artifact_uploads_without_retention(workflows: Path) -> list[str]:
    findings: list[str] = []
    for workflow in sorted(workflows.glob("*.y*ml")):
        lines = workflow.read_text().splitlines()
        for index, line in enumerate(lines):
            if "uses: actions/upload-artifact@" not in line:
                continue
            step_indent = len(line) - len(line.lstrip())
            end = index + 1
            while end < len(lines):
                candidate = lines[end]
                candidate_indent = len(candidate) - len(candidate.lstrip())
                if candidate.strip().startswith("- ") and candidate_indent <= step_indent:
                    break
                end += 1
            retention = next(
                (
                    int(match.group(1))
                    for candidate in lines[index:end]
                    if (match := re.fullmatch(r"\s+retention-days:\s+([1-9][0-9]*)", candidate))
                ),
                None,
            )
            if retention is None or retention > 90:
                findings.append(
                    f"{workflow.relative_to(workflows.parent.parent)}:{index + 1}: "
                    "artifact upload must define retention-days between 1 and 90"
                )
    return findings


def main() -> int:
    findings = (
        outdated_actions(WORKFLOWS)
        + unpinned_actions(WORKFLOWS)
        + checkouts_with_persisted_credentials(WORKFLOWS)
        + workflows_without_concurrency(WORKFLOWS)
        + security_workflows_without_schedule(WORKFLOWS)
        + jobs_without_timeouts(WORKFLOWS)
        + jobs_with_mutable_runner_labels(WORKFLOWS)
        + artifact_uploads_without_retention(WORKFLOWS)
    )
    if findings:
        print("FAIL workflow-supply-chain-hygiene")
        print("\n".join(findings))
        return 1
    print("PASS workflow-supply-chain-hygiene")
    return 0


if __name__ == "__main__":
    sys.exit(main())
