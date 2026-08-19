import contextlib
import io
import subprocess
import unittest

from scripts.retry_command import run_with_retry


class RetryCommandTests(unittest.TestCase):
    def run_quietly(self, *args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return run_with_retry(*args, **kwargs)

    def test_transient_failure_is_retried_then_succeeds(self):
        results = iter([
            subprocess.CompletedProcess([], 1, "", "502 Bad Gateway"),
            subprocess.CompletedProcess([], 0, "built\n", ""),
        ])
        delays = []

        status = self.run_quietly(
            ["docker", "build", "."], 3, 2,
            runner=lambda *args, **kwargs: next(results), sleeper=delays.append,
        )

        self.assertEqual(status, 0)
        self.assertEqual(delays, [2])

    def test_deterministic_failure_is_not_retried(self):
        calls = []

        def fail(*args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess([], 2, "", "Dockerfile parse error")

        status = self.run_quietly(["docker", "build", "."], 3, 0, runner=fail, sleeper=lambda _: None)

        self.assertEqual(status, 2)
        self.assertEqual(len(calls), 1)

    def test_transient_failure_stops_at_attempt_limit(self):
        calls = []

        def unavailable(*args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess([], 1, "", "503 Service Unavailable")

        status = self.run_quietly(["docker", "build", "."], 3, 0, runner=unavailable, sleeper=lambda _: None)

        self.assertEqual(status, 1)
        self.assertEqual(len(calls), 3)
