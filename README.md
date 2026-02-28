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

## Current Status
See `docs/roadmap/SPRINT-7D.md` and `logs/daily/2026-02-23.md`.
