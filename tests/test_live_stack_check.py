import contextlib
import io
import unittest

from scripts.live_stack_check import retry


class LiveStackRetryTests(unittest.TestCase):
    def test_connection_reset_during_startup_is_retried(self):
        outcomes = iter([ConnectionResetError("peer restarting"), True])
        delays = []

        def check():
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with contextlib.redirect_stdout(io.StringIO()):
            retry("Grafana dashboard", check, attempts=2, delay=0.5, sleeper=delays.append)

        self.assertEqual(delays, [0.5])

    def test_persistent_network_failure_reports_last_error(self):
        with self.assertRaisesRegex(RuntimeError, "connection refused"):
            retry(
                "Grafana dashboard",
                lambda: (_ for _ in ()).throw(ConnectionRefusedError("connection refused")),
                attempts=2,
                delay=0,
                sleeper=lambda _: None,
            )
