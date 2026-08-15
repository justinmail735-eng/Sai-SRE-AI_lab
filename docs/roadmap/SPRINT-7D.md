# SentinelSRE enterprise-demo delivery plan

Target: Friday, August 21, 2026.

| Milestone | Outcome | Evidence | Status |
| --- | --- | --- | --- |
| 1. Live reliability lab | Instrumented checkout, OTel, Prometheus, Grafana, controlled faults | Live Compose verifier | Complete |
| 2. Kubernetes platform | Hardened Helm release on a three-node Kind cluster | Manifest and runtime checks | Complete |
| 3. Multi-cloud foundations | Private EKS and AKS Terraform with provider-native controls | Init, validate, TFLint, mocked plans | Complete |
| 4. GitOps and security | Argo CD desired state, admission, scan, SBOM, signing workflow | Positive/negative policy and security gates | Complete |
| 5. Governed agents | Read-only investigation and approval-gated fixed action broker | Denial paths, live recovery, audit hash | Complete |
| 6. Chaos and learning | Application incident, Pod loss, bounded recovery, postmortem | Committed evidence and drift gate | Complete |
| 7. Portfolio delivery | One-command showcase, architecture, interview narrative, hosted UI | 11/11 showcase result and site tests | Complete |

## Next engineering increments

These are intentionally outside the completed demo boundary:

1. Implement read-only CloudWatch/CloudTrail and Azure Monitor/Activity Log
   adapters against dedicated sandbox accounts.
2. Store approvals in KMS/Key Vault and audit events in immutable cloud storage.
3. Add a service catalog and ownership synchronization adapter.
4. Exercise regional and dependency failures with network-level chaos tooling.
5. Promote a signed release through a real non-production Argo CD cluster.
