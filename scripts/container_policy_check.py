#!/usr/bin/env python3
"""Enforce immutable and patched external bases in repository Dockerfiles."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROM_PATTERN = re.compile(
    r"^\s*FROM(?:\s+--platform=\S+)?\s+(?P<image>\S+)"
    r"(?:\s+AS\s+(?P<alias>[A-Za-z0-9_.-]+))?\s*$",
    re.IGNORECASE,
)
DIGEST_PATTERN = re.compile(r".+@sha256:[0-9a-f]{64}$")


def mutable_container_bases(root: Path) -> list[str]:
    findings: list[str] = []
    for dockerfile in sorted(root.rglob("Dockerfile")):
        if ".git" in dockerfile.parts:
            continue
        aliases: set[str] = set()
        for line_number, line in enumerate(dockerfile.read_text().splitlines(), start=1):
            match = FROM_PATTERN.fullmatch(line)
            if not match:
                continue
            image = match.group("image")
            if image.lower() != "scratch" and image not in aliases and not DIGEST_PATTERN.fullmatch(image):
                findings.append(
                    f"{dockerfile.relative_to(root)}:{line_number}: "
                    f"external base {image} must use an immutable sha256 digest"
                )
            if match.group("alias"):
                aliases.add(match.group("alias"))
    return findings


def alpine_images_without_package_upgrade(root: Path) -> list[str]:
    findings: list[str] = []
    for dockerfile in sorted(root.rglob("Dockerfile")):
        if ".git" in dockerfile.parts:
            continue
        lines = dockerfile.read_text().splitlines()
        alpine_lines = [
            line_number
            for line_number, line in enumerate(lines, start=1)
            if (match := FROM_PATTERN.fullmatch(line))
            and "alpine" in match.group("image").split("@", 1)[0].lower()
        ]
        if alpine_lines and not any(
            re.search(r"\bapk\s+upgrade\s+--no-cache\b", line) for line in lines
        ):
            findings.append(
                f"{dockerfile.relative_to(root)}:{alpine_lines[0]}: Alpine image must run "
                "apk upgrade --no-cache so fixed OS packages replace vulnerable base layers"
            )
    return findings


def main() -> int:
    findings = mutable_container_bases(ROOT) + alpine_images_without_package_upgrade(ROOT)
    if findings:
        print("FAIL immutable-container-bases")
        print("\n".join(findings))
        return 1
    print("PASS immutable-container-bases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
