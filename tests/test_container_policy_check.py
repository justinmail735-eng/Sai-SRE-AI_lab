import tempfile
import unittest
from pathlib import Path

from scripts.container_policy_check import (
    alpine_images_without_package_upgrade,
    mutable_container_bases,
)


class ContainerPolicyCheckTests(unittest.TestCase):
    def test_repository_container_bases_are_immutable(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(mutable_container_bases(root), [])
        self.assertEqual(alpine_images_without_package_upgrade(root), [])

    def test_mutable_external_base_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Dockerfile").write_text("FROM python:3.12-alpine\n")
            findings = mutable_container_bases(root)

        self.assertEqual(len(findings), 1)
        self.assertIn("Dockerfile:1", findings[0])
        self.assertIn("immutable sha256 digest", findings[0])

    def test_alpine_image_without_os_upgrade_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Dockerfile").write_text(
                "FROM python:3.12-alpine@sha256:" + "a" * 64 + "\nRUN echo ready\n"
            )
            findings = alpine_images_without_package_upgrade(root)

        self.assertEqual(len(findings), 1)
        self.assertIn("apk upgrade --no-cache", findings[0])

    def test_alpine_no_cache_upgrade_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Dockerfile").write_text(
                "FROM alpine:3.24@sha256:" + "b" * 64 + "\nRUN apk upgrade --no-cache\n"
            )

            self.assertEqual(alpine_images_without_package_upgrade(root), [])


if __name__ == "__main__":
    unittest.main()
