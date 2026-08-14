#!/usr/bin/env python3
"""Validate the GitOps contract using rendered, executable artifacts."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "platform/helm/checkout-api"
GITOPS = ROOT / "platform/gitops"
POLICY = ROOT / "security/policies/conftest"


def command(*args: str, output: Path | None = None) -> str:
    result = subprocess.run(args, cwd=ROOT, check=True, text=True, capture_output=True)
    if output:
        output.write_text(result.stdout)
    return result.stdout


def validate_contract() -> list[str]:
    application = (GITOPS / "checkout-application.yaml").read_text()
    project = (GITOPS / "project.yaml").read_text()
    image_policy = (ROOT / "security/policies/kyverno/verify-checkout-images.yaml").read_text()
    required = {
        "automated reconciliation": "automated:" in application,
        "drift self-healing": "selfHeal: true" in application,
        "safe pruning": "prune: true" in application and "allowEmpty: false" in application,
        "repository allowlist": "sourceRepos:" in project and "Sai-SRE-AI_lab.git" in project,
        "destination allowlist": "destinations:" in project and "namespace: sentinelsre" in project,
        "signature enforcement": "validationFailureAction: Enforce" in image_policy,
        "OIDC identity": "token.actions.githubusercontent.com" in image_policy and "refs/tags/v.*" in image_policy,
        "transparency log": "rekor.sigstore.dev" in image_policy,
    }
    failures = [name for name, passed in required.items() if not passed]
    if failures:
        raise ValueError("GitOps contract failed: " + ", ".join(failures))
    return list(required)


def main() -> int:
    checks = validate_contract()
    command("kustomize", "build", str(GITOPS))
    command("conftest", "verify", "--policy", str(POLICY))
    with tempfile.TemporaryDirectory(prefix="sentinelsre-policy-") as directory:
        rendered = Path(directory) / "checkout.yaml"
        command(
            "helm", "template", "checkout", str(CHART),
            "--namespace", "sentinelsre", "--values", str(CHART / "values-gitops.yaml"),
            output=rendered,
        )
        command("conftest", "test", str(rendered), "--policy", str(POLICY), "--all-namespaces")
    for check in checks:
        print(f"PASS {check}")
    print("PASS rendered Helm manifests satisfy admission policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
