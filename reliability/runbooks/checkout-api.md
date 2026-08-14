# Checkout API Incident Runbook

## Preconditions

- Confirm the alert identifies `checkout-api` and a production environment.
- Record the incident identifier and current on-call owner.
- Use read-only diagnostics before proposing a mutation.

## Diagnostics

1. Compare request, error, latency, and saturation signals.
2. Identify deployments and configuration changes during the preceding 30 minutes.
3. Compare errors by application version, region, and dependency.
4. Confirm whether `orders-api` and `payment-worker` remain healthy.
5. Record supporting and contradicting evidence for each hypothesis.

## Remediation Policy

- A rollback, traffic shift, scale operation, or restart requires an authorized human.
- The action proposal must include blast radius, risk, and a recovery path.
- Do not proceed when telemetry is missing or contradictory evidence is unresolved.

## Verification

- Error rate remains below 1% for five minutes.
- p95 latency remains below 500 ms for five minutes.
- Multi-window error-budget burn is decreasing.
- No dependency or regional regression appears after the action.
