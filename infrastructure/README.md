# Multi-cloud infrastructure

SentinelSRE provides first-party Terraform foundations for Amazon EKS and
Azure Kubernetes Service. They expose the same platform intent while retaining
provider-specific controls instead of hiding them behind a lowest-common-
denominator abstraction.

| Reliability control | AWS EKS | Azure AKS |
| --- | --- | --- |
| Private API | Private endpoint by default | Private cluster by default |
| Identity | Dedicated IAM roles | User-assigned identity and Entra RBAC |
| Workload identity | EKS OIDC issuer | OIDC issuer and workload identity |
| Network isolation | Multi-AZ VPC and private nodes | VNet, subnet, NSG, Azure network policy |
| Auditability | All EKS control-plane logs and VPC flow logs | Log Analytics and Azure Policy |
| Secret protection | Rotating KMS key | Key Vault CSI provider with rotation |
| Availability | Managed node group across 2+ AZs | Autoscaling node pool across 3 zones |

## Validate without cloud credentials

```bash
make terraform-test
```

The gate formats, initializes, validates, and lints both modules and both
environment roots. Native Terraform tests use mocked providers to inspect
planned security and availability properties; they create no cloud resources.

## Real deployment boundary

The checked-in `aws-dev` and `azure-dev` roots are examples, not automatic
deployments. Copy the relevant `terraform.tfvars.example`, authenticate with a
least-privilege deployment identity, configure a remote encrypted backend, and
review a saved plan before applying. An apply creates managed Kubernetes and
supporting resources that incur cloud charges. AWS NAT is deliberately off in
the cost-safe example; production private nodes require an approved egress
design such as NAT gateways and/or VPC endpoints.
