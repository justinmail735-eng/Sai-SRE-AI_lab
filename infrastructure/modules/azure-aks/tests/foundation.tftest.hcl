mock_provider "azurerm" {}

run "private_identity_enabled_foundation" {
  command = plan

  variables {
    name      = "sentinel-dev"
    tenant_id = "00000000-0000-0000-0000-000000000001"
  }

  assert {
    condition     = azurerm_kubernetes_cluster.this.private_cluster_enabled
    error_message = "AKS must use a private API endpoint by default."
  }

  assert {
    condition     = azurerm_kubernetes_cluster.this.local_account_disabled
    error_message = "AKS local accounts must be disabled."
  }

  assert {
    condition     = azurerm_kubernetes_cluster.this.oidc_issuer_enabled && azurerm_kubernetes_cluster.this.workload_identity_enabled
    error_message = "OIDC and workload identity must be enabled."
  }

  assert {
    condition     = azurerm_kubernetes_cluster.this.azure_policy_enabled
    error_message = "Azure Policy must be enabled."
  }

  assert {
    condition     = azurerm_kubernetes_cluster.this.network_profile[0].network_policy == "azure"
    error_message = "AKS network policy must be enabled."
  }

  assert {
    condition     = azurerm_kubernetes_cluster.this.default_node_pool[0].min_count >= 2
    error_message = "The managed node pool must preserve at least two nodes."
  }
}
