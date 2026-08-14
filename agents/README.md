# Governed Engineering Agents

Agents in this repository behave like constrained members of a platform team.
They gather evidence, generate reviewable artifacts, validate their work, and
report risk and approval requirements through the shared `AgentResult` contract.

## Safety Contract

- Read-only discovery, drafting, and local validation may run automatically.
- Generated infrastructure, dashboards, alerts, and policies remain in Git.
- Staging mutations require an environment policy.
- Production and destructive actions always require explicit approval.
- Every action must define a verification step and create an audit result.

## Observability Engineer Agent

The first implemented agent converts a `ServiceObservability` specification into:

- a Grafana golden-signals dashboard;
- Prometheus error-budget and latency alerts;
- a machine-readable agent execution result;
- drift checks that fail when checked-in artifacts no longer match the service specification.

Generate artifacts:

```bash
python3 agents/observability_agent.py \
  --spec reliability/services/checkout-api.json \
  --output-dir observability/generated/checkout-api
```

Verify them without modifying files:

```bash
python3 agents/observability_agent.py \
  --spec reliability/services/checkout-api.json \
  --output-dir observability/generated/checkout-api \
  --check
```
