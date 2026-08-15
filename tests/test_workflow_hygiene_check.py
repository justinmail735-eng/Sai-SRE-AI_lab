import tempfile
import unittest
from pathlib import Path

from scripts.workflow_hygiene_check import outdated_actions


class WorkflowHygieneCheckTests(unittest.TestCase):
    def test_repository_workflows_use_node24_compatible_actions(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(outdated_actions(root / ".github" / "workflows"), [])

    def test_deprecated_first_party_action_is_reported_with_location(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("steps:\n  - uses: actions/checkout@v4\n")
            findings = outdated_actions(workflows)

        self.assertEqual(len(findings), 1)
        self.assertIn("ci.yml:2", findings[0])
        self.assertIn("must be v5 or newer", findings[0])
