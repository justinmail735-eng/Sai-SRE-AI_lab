#!/usr/bin/env python3
"""Generate controlled traffic for the local SentinelSRE demo."""

from __future__ import annotations

import argparse
import time
import urllib.error
import urllib.request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8080/checkout")
    parser.add_argument("--requests-per-second", type=float, default=4)
    parser.add_argument("--duration", type=int, default=0, help="seconds; zero runs until interrupted")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.requests_per_second <= 0 or args.duration < 0:
        print("requests-per-second must be positive and duration cannot be negative")
        return 2
    delay = 1 / args.requests_per_second
    deadline = time.monotonic() + args.duration if args.duration else None
    sent = failures = 0
    try:
        while deadline is None or time.monotonic() < deadline:
            started = time.monotonic()
            try:
                with urllib.request.urlopen(args.url, timeout=5) as response:
                    failures += response.status >= 500
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
                failures += 1
            sent += 1
            remaining = delay - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        pass
    print(f"traffic complete: sent={sent} failures={failures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
