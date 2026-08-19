#!/usr/bin/env python3
"""Verify the running SentinelSRE telemetry path end to end."""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request


def fetch_json(url: str, method: str = "GET") -> object:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def retry(label: str, check, attempts: int = 20, delay: float = 1.0, *, sleeper=time.sleep) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            if check():
                print(f"PASS {label}")
                return
        except (KeyError, TypeError, ValueError, OSError) as exc:
            last_error = exc
        sleeper(delay)
    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(f"{label} did not become ready{detail}")


def prometheus_value(query: str) -> float:
    encoded = urllib.parse.urlencode({"query": query})
    payload = fetch_json(f"http://localhost:9090/api/v1/query?{encoded}")
    result = payload["data"]["result"]
    return float(result[0]["value"][1]) if result else 0.0


def main() -> int:
    try:
        retry(
            "checkout health",
            lambda: fetch_json("http://localhost:8080/healthz")["status"] == "healthy",
        )
        for _ in range(10):
            fetch_json("http://localhost:8080/checkout")

        retry("OpenTelemetry metrics in Prometheus", lambda: prometheus_value("sum(http_server_requests_total)") >= 10)
        retry(
            "agent-generated alert rules loaded",
            lambda: "checkout_api_error_budget_fast_burn"
            in json.dumps(fetch_json("http://localhost:9090/api/v1/rules?type=alert")),
        )
        retry(
            "agent-generated Grafana dashboard provisioned",
            lambda: any(
                item.get("uid") == "sai-checkout-api"
                for item in fetch_json("http://localhost:3001/api/search?query=checkout")
            ),
        )
    except RuntimeError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
