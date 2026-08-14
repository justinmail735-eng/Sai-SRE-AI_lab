#!/usr/bin/env python3
"""Verify a live SentinelSRE Kubernetes deployment and its safeguards."""

from __future__ import annotations

import json
import subprocess
import sys

NAMESPACE = "sentinelsre"
DEPLOYMENT = "checkout-checkout-api"
SELECTOR = "app.kubernetes.io/name=checkout-api"


def kubectl_json(*args: str) -> dict:
    completed = subprocess.run(["kubectl", *args, "-o", "json"], capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip())
    return json.loads(completed.stdout)


def validate_runtime(deployment: dict, pods: dict, pdb: dict, network_policy: dict) -> list[str]:
    errors: list[str] = []
    desired = int(deployment["spec"].get("replicas", 0))
    available = int(deployment.get("status", {}).get("availableReplicas", 0))
    if desired < 2 or available != desired:
        errors.append(f"deployment availability is {available}/{desired}; expected at least two fully available replicas")

    active_pods = [item for item in pods.get("items", []) if not item["metadata"].get("deletionTimestamp")]
    nodes = {item["spec"].get("nodeName") for item in active_pods}
    if len(active_pods) != desired:
        errors.append(f"found {len(active_pods)} active pods; expected {desired}")
    if len(nodes - {None}) < 2:
        errors.append("active replicas are not spread across at least two nodes")

    for pod in active_pods:
        name = pod["metadata"]["name"]
        spec = pod["spec"]
        pod_security = spec.get("securityContext", {})
        container = spec["containers"][0]
        container_security = container.get("securityContext", {})
        if pod_security.get("runAsNonRoot") is not True:
            errors.append(f"{name} is not required to run as non-root")
        if pod_security.get("seccompProfile", {}).get("type") != "RuntimeDefault":
            errors.append(f"{name} does not use RuntimeDefault seccomp")
        if spec.get("automountServiceAccountToken") is not False:
            errors.append(f"{name} may automount its service-account token")
        if container_security.get("allowPrivilegeEscalation") is not False:
            errors.append(f"{name} allows privilege escalation")
        if container_security.get("readOnlyRootFilesystem") is not True:
            errors.append(f"{name} does not use a read-only root filesystem")
        if container_security.get("capabilities", {}).get("drop") != ["ALL"]:
            errors.append(f"{name} does not drop all Linux capabilities")
        for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
            if probe not in container:
                errors.append(f"{name} is missing {probe}")
        resources = container.get("resources", {})
        if not resources.get("requests") or not resources.get("limits"):
            errors.append(f"{name} is missing resource requests or limits")

    pdb_status = pdb.get("status", {})
    if int(pdb_status.get("disruptionsAllowed", 0)) < 1:
        errors.append("pod disruption budget does not currently allow one safe disruption")
    if not network_policy.get("spec", {}).get("policyTypes") == ["Ingress", "Egress"]:
        errors.append("network policy does not govern both ingress and egress")
    return errors


def smoke_service() -> None:
    subprocess.run(
        ["kubectl", "delete", "pod", "checkout-smoke", "-n", NAMESPACE, "--ignore-not-found"],
        capture_output=True,
    )
    command = [
        "kubectl", "run", "checkout-smoke", "-n", NAMESPACE,
        "--image=local-checkout-api:latest", "--image-pull-policy=IfNotPresent",
        "--restart=Never", "--command", "--", "python3", "-c",
        "import json,urllib.request; print(json.load(urllib.request.urlopen('http://checkout-checkout-api/healthz'))['status'])",
    ]
    created = subprocess.run(command, capture_output=True, text=True)
    if created.returncode:
        raise RuntimeError(created.stderr.strip())
    try:
        waited = subprocess.run(
            ["kubectl", "wait", "--for=jsonpath={.status.phase}=Succeeded", "pod/checkout-smoke", "-n", NAMESPACE, "--timeout=60s"],
            capture_output=True,
            text=True,
        )
        logs = subprocess.run(
            ["kubectl", "logs", "checkout-smoke", "-n", NAMESPACE], capture_output=True, text=True
        )
        if waited.returncode or logs.returncode or logs.stdout.strip() != "healthy":
            raise RuntimeError((waited.stderr or logs.stderr or logs.stdout).strip())
    finally:
        subprocess.run(
            ["kubectl", "delete", "pod", "checkout-smoke", "-n", NAMESPACE, "--ignore-not-found"],
            capture_output=True,
        )


def main() -> int:
    try:
        deployment = kubectl_json("get", "deployment", DEPLOYMENT, "-n", NAMESPACE)
        pods = kubectl_json("get", "pods", "-l", SELECTOR, "-n", NAMESPACE)
        pdb = kubectl_json("get", "pdb", DEPLOYMENT, "-n", NAMESPACE)
        policy = kubectl_json("get", "networkpolicy", DEPLOYMENT, "-n", NAMESPACE)
        errors = validate_runtime(deployment, pods, pdb, policy)
        if errors:
            for error in errors:
                print(f"FAIL {error}")
            return 1
        print("PASS deployment replicas are healthy and node-spread")
        print("PASS runtime security and resource safeguards are active")
        print("PASS disruption and network policies are active")
        smoke_service()
        print("PASS in-cluster service request succeeded")
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"FAIL Kubernetes runtime verification: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
