# Controlled reliability experiments

SentinelSRE has two executable, bounded failure exercises.

## Application failure and governed recovery

The checkout workload exposes local-only `errors` and `latency` modes. The
Incident Investigator reads health, customer-path behavior, and metrics; drafts
an action request; and cannot mutate the workload. The Action Broker requires a
separate authorized dummy user, an expiring request-bound approval, and explicit
`--apply` before its fixed recovery adapter runs. Recovery is verified and added
to a hash-chained audit log.

The committed [application incident evidence](../../docs/evidence/INC-DEMO-ERROR/investigation.json)
and [generated postmortem](../../docs/postmortems/INC-DEMO-ERROR.md) came from the
live Docker Compose stack, not a hand-authored scenario.

## Kubernetes Pod loss

Preview the resolved target without mutation:

```bash
make chaos-plan
```

Execute only on the `kind-sentinelsre` context:

```bash
make chaos-k8s
make k8s-verify
```

The runner refuses unless the context, namespace, deployment, two ready
replicas, PodDisruptionBudget, and multi-node spreading all match the lab's
allowlist. It deletes one explicit Pod, then requires a new Pod UID and full
replica recovery within 120 seconds. It never accepts an arbitrary resource or
command. The latest committed evidence recovered 2/2 replicas in 2.443 seconds.

GitHub Actions repeats this Pod-loss test inside an ephemeral Kind cluster on
every change, after the baseline runtime safeguards pass.
