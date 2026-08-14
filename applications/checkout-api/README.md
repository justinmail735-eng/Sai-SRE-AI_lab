# Checkout API

A dependency-free reference workload for SentinelSRE. It exposes:

- `GET /checkout` — simulated checkout request;
- `GET /healthz` — liveness/readiness endpoint;
- `GET /metrics` — Prometheus-compatible golden-signal metrics;
- `POST /admin/fault?mode=none|latency|errors` — local-lab fault control.

The fault endpoint is intentionally limited to the local demo and must not be
deployed as a production administration interface.
