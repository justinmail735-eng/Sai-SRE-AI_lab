import unittest

from scripts.k8s_chaos_check import CONTEXT, select_victim, validate_preconditions


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


if __name__ == "__main__":
    unittest.main()
