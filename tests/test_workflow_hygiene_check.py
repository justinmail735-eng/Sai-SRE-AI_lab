import tempfile
import unittest
from pathlib import Path

from scripts.workflow_hygiene_check import jobs_without_timeouts, outdated_actions, unpinned_actions


class WorkflowHygieneCheckTests(unittest.TestCase):
    def test_repository_workflows_use_node24_compatible_actions(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(outdated_actions(root / ".github" / "workflows"), [])

    def test_repository_actions_are_pinned_to_commits(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(unpinned_actions(root / ".github" / "workflows"), [])

    def test_repository_jobs_have_execution_budgets(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(jobs_without_timeouts(root / ".github" / "workflows"), [])

    def test_deprecated_first_party_action_is_reported_with_location(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("steps:\n  - uses: actions/checkout@v4\n")
            findings = outdated_actions(workflows)

        self.assertEqual(len(findings), 1)
        self.assertIn("ci.yml:2", findings[0])
        self.assertIn("must be v5 or newer", findings[0])

    def test_mutable_action_tag_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "release.yml").write_text("steps:\n  - uses: vendor/release-action@v3\n")
            findings = unpinned_actions(workflows)

        self.assertEqual(len(findings), 1)
        self.assertIn("release.yml:2", findings[0])
        self.assertIn("immutable 40-character commit SHA", findings[0])

    def test_job_without_timeout_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text(
                "name: ci\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
            )
            findings = jobs_without_timeouts(workflows)

        self.assertEqual(len(findings), 1)
        self.assertIn("job test", findings[0])
        self.assertIn("positive timeout-minutes", findings[0])
