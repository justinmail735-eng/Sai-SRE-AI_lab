# Platform Architecture (v0)

## Principles
- Local-first and reproducible.
- Production-style patterns over toy examples.
- Explicit tradeoffs and failure modes.

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

## Non-Goals (for now)
- Vendor-locked integrations.
- Paid APIs as hard requirements.
