module "platform" {
  source = "../../modules/azure-aks"

  name      = "sentinelsre-dev"
  location  = var.location
  tenant_id = var.tenant_id

  tags = {
    Owner      = "platform-sre"
    CostCenter = "sentinelsre-lab"
  }
}
