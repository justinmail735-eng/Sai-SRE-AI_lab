#!/usr/bin/env python3
"""Retry a command only when its output identifies a transient infrastructure failure."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable

TRANSIENT_MARKERS = (
    "429 Too Many Requests",
    "500 Internal Server Error",
    "502 Bad Gateway",
    "503 Service Unavailable",
    "504 Gateway Timeout",
    "connection reset by peer",
    "i/o timeout",
    "TLS handshake timeout",
)


def run_with_retry(
    command: list[str],
    attempts: int,
    base_delay: float,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    for attempt in range(1, attempts + 1):
        completed = runner(command, text=True, capture_output=True)
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode == 0:
            return 0
        combined = f"{completed.stdout}\n{completed.stderr}".lower()
        transient = any(marker.lower() in combined for marker in TRANSIENT_MARKERS)
        if not transient or attempt == attempts:
            return completed.returncode
        delay = base_delay * attempt
        print(
            f"WARN transient command failure; retrying attempt {attempt + 1}/{attempts} in {delay:g}s",
            file=sys.stderr,
        )
        sleeper(delay)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--base-delay", type=float, default=5)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    if args.attempts < 1 or args.base_delay < 0:
        parser.error("--attempts must be positive and --base-delay cannot be negative")
    return run_with_retry(command, args.attempts, args.base_delay)


if __name__ == "__main__":
    raise SystemExit(main())
