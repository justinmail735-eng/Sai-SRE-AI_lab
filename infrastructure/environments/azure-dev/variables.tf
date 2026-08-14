variable "subscription_id" {
  description = "Azure subscription receiving the development foundation."
  type        = string
}

variable "tenant_id" {
  description = "Microsoft Entra tenant used for AKS Azure RBAC."
  type        = string
}

variable "location" {
  type    = string
  default = "eastus"
}
