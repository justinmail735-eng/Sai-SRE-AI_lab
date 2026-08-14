# Supply-chain controls

SentinelSRE treats an image as deployable only after source, dependencies,
configuration, and the built container pass automated gates.

1. Trivy fails on high or critical known vulnerabilities, IaC
   misconfigurations, and committed secrets.
2. Syft emits a CycloneDX SBOM retained as CI evidence.
3. Helm renders the exact GitOps values and Conftest enforces immutable images,
   resources, and container hardening.
4. Tagged releases publish to GHCR and Cosign signs the exact registry digest
   using GitHub's short-lived OIDC identity.
5. The included Kyverno policy fails closed and admits only images signed by
   tagged executions of this repository's supply-chain workflow.

Run the credential-free local gate with `make security-check`. Signature
verification happens after a tagged image is published; it is intentionally not
simulated with a repository private key.
