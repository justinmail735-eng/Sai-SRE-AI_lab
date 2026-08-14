#!/usr/bin/env python3
"""Small observable checkout service used by the SentinelSRE reliability lab."""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BUCKETS_MS = (25, 50, 100, 250, 500, 1000, 2500, 5000)


class ServiceState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.fault_mode = "none"
        self.started_at = time.monotonic()
        self.requests: dict[str, int] = defaultdict(int)
        self.duration_count = 0
        self.duration_sum_ms = 0.0
        self.duration_buckets = {bucket: 0 for bucket in BUCKETS_MS}

    def set_fault(self, mode: str) -> None:
        if mode not in {"none", "latency", "errors"}:
            raise ValueError("mode must be none, latency, or errors")
        with self.lock:
            self.fault_mode = mode

    def record(self, status_code: int, duration_ms: float) -> None:
        with self.lock:
            self.requests[str(status_code)] += 1
            self.duration_count += 1
            self.duration_sum_ms += duration_ms
            for bucket in BUCKETS_MS:
                if duration_ms <= bucket:
                    self.duration_buckets[bucket] += 1

    def metrics(self) -> str:
        with self.lock:
            lines = [
                "# HELP http_server_requests_total Total HTTP checkout requests.",
                "# TYPE http_server_requests_total counter",
            ]
            for status, count in sorted(self.requests.items()):
                lines.append(f'http_server_requests_total{{service="checkout-api",status_code="{status}"}} {count}')
            lines.extend(
                [
                    "# HELP http_server_request_duration_milliseconds Checkout request duration.",
                    "# TYPE http_server_request_duration_milliseconds histogram",
                ]
            )
            for bucket, count in self.duration_buckets.items():
                lines.append(
                    'http_server_request_duration_milliseconds_bucket'
                    f'{{service="checkout-api",le="{bucket}"}} {count}'
                )
            lines.append(
                'http_server_request_duration_milliseconds_bucket'
                f'{{service="checkout-api",le="+Inf"}} {self.duration_count}'
            )
            lines.append(
                'http_server_request_duration_milliseconds_sum'
                f'{{service="checkout-api"}} {self.duration_sum_ms:.3f}'
            )
            lines.append(
                'http_server_request_duration_milliseconds_count'
                f'{{service="checkout-api"}} {self.duration_count}'
            )
            lines.extend(
                [
                    "# HELP process_cpu_seconds_total Approximate service process CPU time.",
                    "# TYPE process_cpu_seconds_total counter",
                    f'process_cpu_seconds_total{{service="checkout-api"}} {time.process_time():.6f}',
                    "# HELP sentinel_sre_fault_mode Active local fault mode.",
                    "# TYPE sentinel_sre_fault_mode gauge",
                ]
            )
            for mode in ("none", "latency", "errors"):
                active = 1 if mode == self.fault_mode else 0
                lines.append(f'sentinel_sre_fault_mode{{service="checkout-api",mode="{mode}"}} {active}')
            return "\n".join(lines) + "\n"


class CheckoutHandler(BaseHTTPRequestHandler):
    state = ServiceState()
    rng = random.Random(735)

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/healthz":
            self._json(200, {"status": "healthy", "service": "checkout-api"})
            return
        if route == "/metrics":
            body = self.state.metrics().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route != "/checkout":
            self._json(404, {"error": "not found"})
            return

        started = time.monotonic()
        mode = self.state.fault_mode
        if mode == "latency":
            time.sleep(0.65)
        else:
            time.sleep(0.01)
        status = 503 if mode == "errors" and self.rng.random() < 0.8 else 200
        duration_ms = (time.monotonic() - started) * 1000
        self.state.record(status, duration_ms)
        self._json(
            status,
            {
                "status": "accepted" if status == 200 else "unavailable",
                "service": "checkout-api",
                "duration_ms": round(duration_ms, 2),
                "fault_mode": mode,
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/admin/fault":
            self._json(404, {"error": "not found"})
            return
        mode = parse_qs(parsed.query).get("mode", [""])[0]
        try:
            self.state.set_fault(mode)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(200, {"fault_mode": mode, "scope": "local-demo-only"})

    def log_message(self, message: str, *args: object) -> None:
        print(f"checkout-api {self.address_string()} {message % args}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    server = ThreadingHTTPServer((args.host, args.port), CheckoutHandler)
    print(f"checkout-api listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
