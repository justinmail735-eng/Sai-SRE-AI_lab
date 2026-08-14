# Multi-Cloud Platform Architecture (v1)

## Principles
- Local-first and reproducible.
- Production-style patterns over toy examples.
- Explicit tradeoffs and failure modes.
- Provider-neutral core with thin, testable cloud adapters.
- Read-only discovery and diagnosis by default.
- Human approval for production remediation.

## System Boundary

The platform does not replace CloudWatch, Azure Monitor, or an incident-management
system. It consumes their signals, converts them to a shared reliability model,
and coordinates SLO evaluation, evidence-based triage, runbook selection, and
postmortem generation.

```text
AWS CloudWatch / CloudTrail ---- AWS adapter ---\
                                              +--> normalized events
Azure Monitor / Activity Log --- Azure adapter --/          |
                                                              v
SLO Guardian -> Incident Commander -> Triage Agent -> Runbook Agent
                                                              |
                                                              v
                                                    Postmortem Agent
```

## Cloud Adapter Contract

Each provider adapter converts native resources into the same core objects:

- `Service`: identity, provider, region, environment, and owner.
- `ReliabilitySignal`: metric, log, alert, or dependency symptom.
- `ChangeEvent`: deployment, configuration, or infrastructure change.
- `IncidentEvidence`: timestamped fact with source and correlation metadata.
- `RunbookAction`: proposed action, risk, approval requirement, and audit result.

The first adapters target AWS and Azure. A future provider can implement the
same contract without changing the agent workflow.

## Planned Components
1. **slo-engine**
   - Inputs: SLI metrics snapshots / synthetic data
   - Outputs: policy pass/fail, burn-rate warnings

2. **incident-sim**
   - Simulates realistic outage/failure patterns
   - Produces event streams for testing response logic

3. **observability-pack**
   - Baseline dashboards and alerts for core golden signals
   - Alert tuning and routing guidance

4. **triage-assistant**
   - Summarizes incidents from local artifacts
   - Suggests next runbook actions

5. **cloud-adapters**
   - AWS CloudWatch, CloudWatch Logs, and CloudTrail ingestion
   - Azure Monitor, Log Analytics, and Activity Log ingestion
   - Offline fixtures for deterministic demos and tests

6. **agent-workflow**
   - SLO Guardian, Incident Commander, Triage, Runbook, and Postmortem agents
   - Evidence and confidence attached to every diagnosis
   - Approval boundary around mutating cloud actions

## Non-Goals (for now)
- Vendor-locked integrations.
- Paid APIs as hard requirements.
- Autonomous production changes without an explicit approval policy.
