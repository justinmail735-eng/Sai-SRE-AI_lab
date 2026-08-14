# Project 03 — Observability Stack

The implemented Observability Engineer Agent creates a reproducible baseline from
a versioned service specification:

- Grafana golden-signal dashboards;
- multi-window error-budget and latency alerts;
- service ownership and runbook routing;
- deterministic generation and drift validation;
- an auditable agent result containing evidence, risk, and validation outcomes.

The repository check runs on every push, every pull request, manual dispatch, and
every six hours. It fails when generated observability drifts from its source
specification or the checked SLO snapshot violates policy.

```bash
python3 scripts/reliability_check.py
```

This scheduled job continuously validates checked-in fixtures and policies. Live
cloud monitoring will require an explicitly configured AWS, Azure, Prometheus, or
OpenTelemetry connection; the project does not label fixture checks as live-cloud
coverage.
