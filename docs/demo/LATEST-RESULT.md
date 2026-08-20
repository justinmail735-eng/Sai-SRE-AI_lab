# Latest full showcase result

The completed release run on 2026-08-15 passed **12/12 checks** in approximately
46 seconds, including the tested and linted portfolio gate.

| Capability | Result |
| --- | --- |
| Python unit and behavior tests | PASS — 200 tests as of 2026-08-20 |
| Continuous reliability contracts | PASS |
| AWS and Azure Terraform | PASS — 3 mocked plans |
| GitOps and admission policy | PASS |
| Supply-chain gate and SBOM | PASS |
| Portfolio build, rendered HTML, and lint | PASS |
| Live Docker Compose observability | PASS |
| OpenTelemetry → Prometheus → Grafana | PASS |
| Governed incident recovery | PASS |
| Hardened Kubernetes runtime | PASS |
| One-Pod-loss experiment | PASS — recovered in 3.628 seconds during this run |
| Post-chaos runtime verification | PASS |

Safety scope: local Docker and `kind-sentinelsre`; no cloud apply or production
mutation. The complete per-command output remains reproducible through
`make showcase` and is written to the ignored `build/showcase` evidence folder.
