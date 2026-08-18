import unittest

from scripts.k8s_chaos_check import CONTEXT, recovery_status, select_victim, validate_preconditions


def fixtures(replicas=2, ready=2, nodes=("worker-a", "worker-b"), min_available=1):
    deployment = {"spec": {"replicas": replicas}, "status": {"readyReplicas": ready}}
    pdb = {"spec": {"minAvailable": min_available}}
    pods = {"items": [
        {
            "metadata": {"name": f"checkout-{index}", "uid": f"uid-{index}"},
            "spec": {"nodeName": node},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }
        for index, node in enumerate(nodes)
    ]}
    return deployment, pdb, pods


class KubernetesChaosTests(unittest.TestCase):
    def test_safe_multi_node_preconditions_pass(self):
        deployment, pdb, pods = fixtures()
        self.assertEqual(validate_preconditions(CONTEXT, deployment, pdb, pods), [])

    def test_wrong_cluster_is_rejected(self):
        deployment, pdb, pods = fixtures()
        self.assertIn("current context", validate_preconditions("production", deployment, pdb, pods)[0])

    def test_single_replica_is_rejected(self):
        deployment, pdb, pods = fixtures(replicas=1, ready=1, nodes=("worker-a",))
        self.assertTrue(any("at least two" in failure for failure in validate_preconditions(CONTEXT, deployment, pdb, pods)))

    def test_same_node_placement_is_rejected(self):
        deployment, pdb, pods = fixtures(nodes=("worker-a", "worker-a"))
        self.assertTrue(any("spread" in failure for failure in validate_preconditions(CONTEXT, deployment, pdb, pods)))

    def test_victim_selection_is_deterministic(self):
        _, _, pods = fixtures()
        self.assertEqual(select_victim(pods), "checkout-0")

    def test_terminating_ready_pod_does_not_signal_recovery(self):
        deployment, _, pods = fixtures()
        deployment["status"]["availableReplicas"] = 1
        pods["items"][0]["metadata"]["deletionTimestamp"] = "2026-08-18T13:09:07Z"
        pods["items"].append({
            "metadata": {"name": "checkout-replacement", "uid": "uid-new"},
            "spec": {"nodeName": "worker-a"},
            "status": {"conditions": [{"type": "Ready", "status": "False"}]},
        })

        recovered, detail = recovery_status(deployment, pods, {"uid-0", "uid-1"})

        self.assertFalse(recovered)
        self.assertIn("active_ready=1/2", detail)
        self.assertIn("available=1/2", detail)

    def test_ready_replacement_and_full_availability_signal_recovery(self):
        deployment, _, pods = fixtures()
        deployment["status"]["availableReplicas"] = 2
        pods["items"][0]["metadata"]["uid"] = "uid-new"

        recovered, detail = recovery_status(deployment, pods, {"uid-0", "uid-1"})

        self.assertTrue(recovered)
        self.assertIn("ready_replacement_observed=True", detail)


if __name__ == "__main__":
    unittest.main()
