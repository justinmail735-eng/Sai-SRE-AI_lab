package main

import rego.v1

test_rejects_unpinned_sentinelsre_image if {
  failures := deny with input as deployment("ghcr.io/justinmail735-eng/sentinelsre/checkout-api:main")
  "checkout must pin SentinelSRE images by digest" in failures
}

test_accepts_pinned_hardened_image if {
  failures := deny with input as deployment("ghcr.io/justinmail735-eng/sentinelsre/checkout-api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
  count(failures) == 0
}

deployment(image) := {
  "kind": "Deployment",
  "metadata": {"name": "checkout"},
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "image": image,
          "securityContext": {
            "allowPrivilegeEscalation": false,
            "readOnlyRootFilesystem": true,
          },
          "resources": {
            "requests": {"cpu": "50m"},
            "limits": {"memory": "128Mi"},
          },
        }],
      },
    },
  },
}
