# Project 01 — SLO Engine

Build a lightweight SLO policy engine that:
- reads SLO definitions,
- evaluates budget burn behavior,
- fails CI when reliability risk crosses thresholds.

## Delivered Baseline (v1)
- JSON SLO policy schema with service-level windows
- `scripts/slo_check.py` evaluator CLI
- sample service policy: `projects/01-slo-engine/sample-slo.json`
- CI integration gate for critical burn-rate breaches

## Usage
```bash
python3 scripts/slo_check.py --input projects/01-slo-engine/sample-slo.json
```

Exit codes:
- `0` = all services pass / warning only
- `1` = at least one service is in critical burn
- `2` = invalid policy / evaluator failure

Optional ownership guardrail:
- add `owner` on each service and run with `--require-owner` to fail CI when ownership metadata is missing
