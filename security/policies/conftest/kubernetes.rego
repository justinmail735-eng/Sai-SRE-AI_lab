package main

import rego.v1

deny contains msg if {
  input.kind == "Deployment"
  container := input.spec.template.spec.containers[_]
  endswith(container.image, ":latest")
  msg := sprintf("%s uses mutable latest image", [input.metadata.name])
}

deny contains msg if {
  input.kind == "Deployment"
  container := input.spec.template.spec.containers[_]
  startswith(container.image, "ghcr.io/justinmail735-eng/sentinelsre/")
  not contains(container.image, "@sha256:")
  msg := sprintf("%s must pin SentinelSRE images by digest", [input.metadata.name])
}

deny contains msg if {
  input.kind == "Deployment"
  container := input.spec.template.spec.containers[_]
  container.securityContext.allowPrivilegeEscalation != false
  msg := sprintf("%s allows privilege escalation", [input.metadata.name])
}

deny contains msg if {
  input.kind == "Deployment"
  container := input.spec.template.spec.containers[_]
  container.securityContext.readOnlyRootFilesystem != true
  msg := sprintf("%s requires a read-only root filesystem", [input.metadata.name])
}

deny contains msg if {
  input.kind == "Deployment"
  container := input.spec.template.spec.containers[_]
  not container.resources.requests.cpu
  msg := sprintf("%s has no CPU request", [input.metadata.name])
}

deny contains msg if {
  input.kind == "Deployment"
  container := input.spec.template.spec.containers[_]
  not container.resources.limits.memory
  msg := sprintf("%s has no memory limit", [input.metadata.name])
}
