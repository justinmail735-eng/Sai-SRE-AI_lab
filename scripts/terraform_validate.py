#!/usr/bin/env python3
"""Reproducible validation gate for SentinelSRE Terraform roots."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFRASTRUCTURE = ROOT / "infrastructure"
MODULES = ("modules/aws-eks", "modules/azure-aks")
ENVIRONMENTS = ("environments/aws-dev", "environments/azure-dev")


def run(*command: str, cwd: Path = ROOT) -> None:
    print(f"[terraform-check] {cwd.relative_to(ROOT)}: {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    for executable in ("terraform", "tflint"):
        if not shutil.which(executable):
            parser.error(f"{executable} is required")

    run("terraform", "fmt", "-check", "-recursive", str(INFRASTRUCTURE))

    for relative in (*MODULES, *ENVIRONMENTS):
        directory = INFRASTRUCTURE / relative
        run("terraform", "init", "-backend=false", "-input=false", cwd=directory)
        run("terraform", "validate", cwd=directory)
        run("tflint", "--no-color", cwd=directory)

    if not args.skip_tests:
        for relative in MODULES:
            run("terraform", "test", cwd=INFRASTRUCTURE / relative)

    print("[terraform-check] AWS and Azure foundations passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
