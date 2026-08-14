import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "k8s_validate.py"
CHART = ROOT / "platform" / "helm" / "checkout-api"


class KubernetesValidationTests(unittest.TestCase):
    def test_default_chart_passes_enterprise_invariants(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS Helm chart renders", result.stdout)
        self.assertIn("PASS Kubernetes workload safeguards", result.stdout)

    def test_helm_lint_passes(self):
        result = subprocess.run(["helm", "lint", str(CHART)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_kind_values_disable_hpa_but_keep_pdb(self):
        result = subprocess.run(
            ["helm", "template", "sentinel", str(CHART), "-f", str(CHART / "values-kind.yaml")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("kind: HorizontalPodAutoscaler", result.stdout)
        self.assertIn("kind: PodDisruptionBudget", result.stdout)
        self.assertIn("replicas: 2", result.stdout)

    def test_render_has_no_default_service_account_token(self):
        result = subprocess.run(["helm", "template", "sentinel", str(CHART)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(result.stdout.count("automountServiceAccountToken: false"), 2)
