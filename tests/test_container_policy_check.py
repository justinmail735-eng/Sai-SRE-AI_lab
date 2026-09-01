import tempfile
import unittest
from pathlib import Path

from scripts.container_policy_check import mutable_container_bases


class ContainerPolicyCheckTests(unittest.TestCase):
    def test_repository_container_bases_are_immutable(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(mutable_container_bases(root), [])

    def test_mutable_external_base_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Dockerfile").write_text("FROM python:3.12-alpine\n")
            findings = mutable_container_bases(root)

        self.assertEqual(len(findings), 1)
        self.assertIn("Dockerfile:1", findings[0])
        self.assertIn("immutable sha256 digest", findings[0])


if __name__ == "__main__":
    unittest.main()
