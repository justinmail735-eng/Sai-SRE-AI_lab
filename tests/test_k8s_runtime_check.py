import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "k8s_runtime_check.py"
SPEC = importlib.util.spec_from_file_location("k8s_runtime", SCRIPT)
k8s_runtime = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(k8s_runtime)


def healthy_fixture():
    container = {
        "startupProbe": {}, "readinessProbe": {}, "livenessProbe": {},
        "resources": {"requests": {"cpu": "50m"}, "limits": {"cpu": "500m"}},
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
        },
    }
    pod = lambda name, node: {
        "metadata": {"name": name},
        "spec": {
            "nodeName": node,
            "automountServiceAccountToken": False,
            "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [container],
        },
    }
    return (
        {"spec": {"replicas": 2}, "status": {"availableReplicas": 2}},
        {"items": [pod("one", "worker-a"), pod("two", "worker-b")]},
        {"status": {"disruptionsAllowed": 1}},
        {"spec": {"policyTypes": ["Ingress", "Egress"]}},
    )


class KubernetesRuntimeValidationTests(unittest.TestCase):
    def test_healthy_runtime_snapshot_passes(self):
        self.assertEqual(k8s_runtime.validate_runtime(*healthy_fixture()), [])

    def test_same_node_replicas_fail_spread_check(self):
        deployment, pods, pdb, policy = healthy_fixture()
        pods["items"][1]["spec"]["nodeName"] = "worker-a"
        errors = k8s_runtime.validate_runtime(deployment, pods, pdb, policy)
        self.assertIn("active replicas are not spread across at least two nodes", errors)

    def test_privilege_regression_is_detected(self):
        deployment, pods, pdb, policy = healthy_fixture()
        pods["items"][0]["spec"]["containers"][0]["securityContext"]["allowPrivilegeEscalation"] = True
        errors = k8s_runtime.validate_runtime(deployment, pods, pdb, policy)
        self.assertTrue(any("allows privilege escalation" in error for error in errors))

    def test_unavailable_replica_is_detected(self):
        deployment, pods, pdb, policy = healthy_fixture()
        deployment["status"]["availableReplicas"] = 1
        errors = k8s_runtime.validate_runtime(deployment, pods, pdb, policy)
        self.assertTrue(any("deployment availability" in error for error in errors))
