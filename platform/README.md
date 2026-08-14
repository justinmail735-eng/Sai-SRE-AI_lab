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
