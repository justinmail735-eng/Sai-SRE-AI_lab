import importlib.util
import io
import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "applications" / "checkout-api" / "app.py"
SPEC = importlib.util.spec_from_file_location("checkout_app", APP)
checkout_app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(checkout_app)


class CheckoutApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        checkout_app.CheckoutHandler.state = checkout_app.ServiceState()
        cls.server = checkout_app.ThreadingHTTPServer(("127.0.0.1", 0), checkout_app.CheckoutHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        checkout_app.CheckoutHandler.state.set_fault("none")

    def request(self, path, method="GET"):
        request = urllib.request.Request(self.base + path, method=method)
        return urllib.request.urlopen(request, timeout=3)

    def test_health_endpoint(self):
        with self.request("/healthz") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response)["status"], "healthy")

    def test_checkout_records_prometheus_metrics(self):
        with self.request("/checkout") as response:
            self.assertEqual(response.status, 200)
        with self.request("/metrics") as response:
            metrics = response.read().decode()
        self.assertIn('http_server_requests_total{service="checkout-api",status_code="200"}', metrics)
        self.assertIn("http_server_request_duration_milliseconds_bucket", metrics)
        self.assertIn('process_cpu_seconds_total{service="checkout-api"}', metrics)

    def test_error_fault_returns_service_unavailable(self):
        checkout_app.CheckoutHandler.rng.seed(1)
        with self.request("/admin/fault?mode=errors", method="POST") as response:
            self.assertEqual(json.load(response)["fault_mode"], "errors")
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/checkout")
        self.assertEqual(context.exception.code, 503)

    def test_invalid_fault_mode_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/admin/fault?mode=delete-everything", method="POST")
        self.assertEqual(context.exception.code, 400)

    def test_metrics_expose_exactly_one_active_fault_mode(self):
        checkout_app.CheckoutHandler.state.set_fault("latency")
        metrics = checkout_app.CheckoutHandler.state.metrics()
        active = [line for line in metrics.splitlines() if "sentinel_sre_fault_mode" in line and line.endswith(" 1")]
        self.assertEqual(active, ['sentinel_sre_fault_mode{service="checkout-api",mode="latency"} 1'])
