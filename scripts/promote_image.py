#!/usr/bin/env python3
"""Safely draft an immutable GitOps image promotion."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VALUES = ROOT / "platform/helm/checkout-api/values-gitops.yaml"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
DIGEST_LINE = re.compile(r'(?m)^(\s*digest:\s*)"?sha256:[0-9a-f]{64}"?(\s*)$')


def render_promotion(content: str, digest: str) -> str:
    if not DIGEST.fullmatch(digest):
        raise ValueError("digest must be sha256 followed by exactly 64 lowercase hex characters")
    updated, count = DIGEST_LINE.subn(rf'\1"{digest}"\2', content)
    if count != 1:
        raise ValueError(f"expected exactly one existing digest, found {count}")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--values", type=Path, default=DEFAULT_VALUES)
    parser.add_argument("--write", action="store_true", help="Apply the draft locally; default is preview only")
    args = parser.parse_args()

    original = args.values.read_text()
    updated = render_promotion(original, args.digest)
    if args.write:
        args.values.write_text(updated)
        print(f"Updated {args.values} to {args.digest}; review and open a promotion PR.")
    else:
        print(updated, end="")
        print("\nPreview only. Re-run with --write to draft the reviewed GitOps change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
