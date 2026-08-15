# SentinelSRE demonstration guide

## One-command showcase

The complete local demonstration is:

```bash
make showcase
```

It requires Docker, Python 3, Helm, Kind, kubectl, Terraform, TFLint,
Kustomize, Conftest, Trivy, and Syft. On macOS with Homebrew:

```bash
brew install helm kind kubectl terraform tflint kustomize conftest trivy syft
```

The command explicitly acknowledges local-only fault injection. It creates or
reuses only `kind-sentinelsre`, starts the Docker Compose lab, and never performs
a cloud apply. It emits `build/showcase/REPORT.md` and machine-readable JSON.

To stop the retained lab afterward:

```bash
make demo-down
make k8s-down
```

## What the audience sees

1. **Prove the system first.** Show the generated report with all capability
   checks, then explain that every claim maps to executable evidence.
2. **Open Grafana.** Visit `http://localhost:3001` and show the generated
   golden-signals dashboard. Prometheus is at `http://localhost:9090`.
3. **Explain the incident.** A real checkout request returns 503 while the
   process health endpoint remains green. The investigator cites both supporting
   and contradicting evidence.
4. **Show governance.** Unapproved execution fails. The observer role fails.
   The dummy incident commander approves the exact digest; the fixed recovery
   adapter runs and verifies fault state plus health.
5. **Show resilience.** One exact checkout Pod is deleted in the three-node Kind
   cluster. A replacement UID appears and the deployment returns to 2/2 ready.
6. **Show multi-cloud depth.** Compare the EKS and AKS Terraform modules and
   explain why provider-native security controls remain visible.
7. **Close with learning.** Open the generated postmortem and its linked request
   and audit hashes.

## Five-minute interview narrative

“SentinelSRE is not an autonomous production bot. It is a governed reliability
workflow. I built a real checkout workload and wired its metrics through
OpenTelemetry, Prometheus, and Grafana. I packaged it with a hardened Helm chart
and proved recovery by deleting a Pod. I expressed equivalent platform intent
for private EKS and AKS using provider-native Terraform. The investigator can
gather evidence and propose an action, but only a separate action broker can
mutate—and only after scope policy, role checks, signed approval, verification,
and audit. The one-command showcase reruns every layer and produces evidence.”

## Useful direct checks

| Goal | Command |
| --- | --- |
| Unit and behavior suite | `make test` |
| Continuous reliability contract | `make check` |
| Live observability path | `make demo-up && make demo-verify` |
| Kubernetes safeguards | `make k8s-validate` |
| Pod-loss recovery | `make chaos-k8s` |
| Both cloud foundations | `make terraform-test` |
| GitOps admission | `make gitops-validate` |
| Supply chain | `make security-check` |
| Committed evidence integrity | `make evidence-check` |
