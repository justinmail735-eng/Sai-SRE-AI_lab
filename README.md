# Sai SRE AI Lab

A senior-level SRE/DevOps/AIOps portfolio built through daily execution.

## Mission
Build production-style reliability systems, runbooks, and automation that demonstrate senior SRE judgment:
- SLO/error-budget design
- Incident simulation + response automation
- Observability and alert quality
- Platform reliability guardrails
- AIOps-assisted triage workflows

## 7-Day Sprint (40-day output style)
- Day 1: Foundation, architecture, roadmap, standards
- Day 2: SLO engine v1 + policy checks
- Day 3: Incident simulator + runbook router
- Day 4: Observability stack + golden signals
- Day 5: Alert quality scoring + dedupe heuristics
- Day 6: AIOps triage assistant (local-first)
- Day 7: Portfolio polish + blog pack + demos

## Repo Layout
- `projects/` — hands-on systems and tools
- `docs/` — architecture, runbooks, decision records
- `blog/` — weekly engineering writeups
- `logs/daily/` — daily progress and outcomes
- `scripts/` — utility tooling and automation

## SLO Policy Evaluator
Run the checker locally against the sample policy:

```bash
python3 scripts/slo_check.py --input projects/01-slo-engine/sample-slo.json
```

Helpful CI/automation flags:
- `--output json` for machine-readable output in pipelines
- `--fail-on-warning` to fail builds on warning-level budget burn
- `--fail-on-insufficient-data` to enforce minimum traffic confidence before passing CI
- `--require-owner` to enforce service ownership metadata (non-empty `owner` per service)

Nightly report generator:
```bash
python3 scripts/nightly_report.py --input projects/01-slo-engine/sample-slo.json --output markdown
```

Useful gates for nightly automation:
- `--fail-on-warning` to fail nightly checks on warning-level burn
- `--fail-on-insufficient-data` to fail nightly checks when windows lack minimum traffic volume
- `--require-owner` to require an owner on every service
- `--service-regex` to focus evaluation/report output to matching service names (for example `^checkout-`)
- `policy.required_windows` (JSON field) to enforce a standard set of burn windows across every service (for example `["5m", "60m"]`)
- `policy.owner_email_domain` (JSON field) to enforce service owner email domains (for example `"sai-lab.local"`)
- `policy.window_burn_rate_overrides` (JSON field) to tune warning/critical burn thresholds by window label (for example stricter `5m` thresholds than `1h`)
- `policy.min_requests_overrides` (JSON field) to set per-window traffic minimums for insufficient-data classification (for example higher confidence requirements on `1h` than `5m`)
- `policy.window_minutes` (JSON field) to enforce canonical duration per window label across services (for example always `5m` = `5`, `1h` = `60`)
- `policy.max_insufficient_windows` (JSON field) to tolerate a bounded number of low-traffic windows before downgrading a service to `insufficient-data` (default `0` preserves strict behavior)

## Current Status
See `docs/roadmap/SPRINT-7D.md` and `logs/daily/2026-02-23.md`.
