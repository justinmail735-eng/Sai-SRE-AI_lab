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

## Implemented agents

The **Observability Engineer Agent** converts a `ServiceObservability`
specification into:

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

The **Incident Investigator Agent** collects evidence directly from the live
reference workload. It ranks an evidence-backed hypothesis and may draft a
typed action request, but it has no execution capability:

```bash
make demo-fault-errors
make agent-investigate
```

The **Action Broker** is the only mutation boundary. Its default is dry-run.
An apply must pass all of these independent checks:

- exact action, target, environment, requester, and parameter allowlists;
- environment execution policy and blast-radius limits;
- active approver identity with an authorized role;
- separation of requester and approver;
- unexpired HMAC approval bound to the complete request digest;
- fixed execution adapters without arbitrary shell input;
- post-action verification and a hash-chained audit record.

Review a proposal without changing anything:

```bash
python3 agents/action_broker.py execute \
  --request build/agent-demo/action-request.json
```

For the local dummy-user demo, provide an ephemeral key through the environment,
approve as the seeded incident commander, then explicitly apply:

```bash
export SENTINELSRE_APPROVAL_KEY='replace-with-at-least-32-characters'
python3 agents/action_broker.py approve \
  --request build/agent-demo/action-request.json \
  --approver sai.demo \
  --output build/agent-demo/approval.json
python3 agents/action_broker.py execute \
  --request build/agent-demo/action-request.json \
  --approval build/agent-demo/approval.json \
  --audit-log build/agent-demo/actions.jsonl \
  --apply
python3 agents/action_broker.py verify-audit \
  --audit-log build/agent-demo/actions.jsonl
```

`demo-identities.json` contains active, unauthorized, and disabled dummy users
so role and lifecycle denials are reproducible. The local HMAC and hash chain
demonstrate the control protocol; a production implementation would place the
approval key in KMS/Key Vault and copy audit events to immutable external
storage. A hash chain detects local tampering but does not make a writable local
file tamper-proof.
