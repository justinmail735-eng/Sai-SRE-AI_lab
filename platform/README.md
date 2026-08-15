# SentinelSRE Platform Layer

The platform layer packages the reference workloads for consistent operation
across local Kubernetes, EKS, and AKS targets.

## Checkout Helm Chart

The chart includes:

- non-root execution, RuntimeDefault seccomp, read-only root filesystem, and all
  Linux capabilities dropped;
- startup, readiness, and liveness probes;
- CPU/memory requests and limits;
- zero-unavailable rolling updates and graceful termination;
- horizontal autoscaling for environments with Metrics Server;
- a PodDisruptionBudget;
- default ingress/egress NetworkPolicy;
- disabled service-account token automounting;
- topology spreading and preferred anti-affinity.

Validate without a cluster:

```bash
make k8s-validate
```

Run and verify on a three-node Kind cluster:

```bash
make k8s-up
make k8s-verify
make k8s-down
```

The Kind values intentionally disable the HPA because Metrics Server is not a
dependency of the minimal lab. The default chart keeps it enabled for managed
cluster environments.

The runtime job also executes a bounded single-Pod-loss experiment and requires
a replacement UID plus full replica recovery within two minutes. See the
[chaos guide](../reliability/chaos/README.md) for the safety preconditions and
captured evidence.

## GitOps delivery

`platform/gitops` defines an Argo CD project with repository/destination
allowlists and an Application with automated pruning, drift self-healing,
retries, and server-side apply. After Argo CD is installed, bootstrap it with:

```bash
kubectl apply -k platform/gitops
```

The production values pin the container by digest. The checked-in digest is a
non-runnable promotion sentinel, so cloning the repository cannot accidentally
deploy an unsigned development image. After a tagged release is scanned,
published, signed, and verified, draft the reviewed GitOps change with:

```bash
python3 scripts/promote_image.py --digest sha256:<64-hex-characters> --write
make gitops-validate
```
