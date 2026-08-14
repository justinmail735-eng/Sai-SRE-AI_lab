variable "name" {
  description = "Short environment name used for resource naming."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.name))
    error_message = "name must be a lowercase DNS-style value between 3 and 31 characters."
  }
}

variable "location" {
  type    = string
  default = "eastus"
}

variable "tenant_id" {
  description = "Microsoft Entra tenant ID used by AKS Azure RBAC."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F-]{36}$", var.tenant_id))
    error_message = "tenant_id must be a UUID."
  }
}

variable "vnet_cidr" {
  type    = string
  default = "10.50.0.0/16"

  validation {
    condition     = can(cidrhost(var.vnet_cidr, 1))
    error_message = "vnet_cidr must be a valid IPv4 CIDR."
  }
}

variable "aks_subnet_cidr" {
  type    = string
  default = "10.50.0.0/20"

  validation {
    condition     = can(cidrhost(var.aks_subnet_cidr, 1))
    error_message = "aks_subnet_cidr must be a valid IPv4 CIDR."
  }
}

variable "kubernetes_version" {
  type    = string
  default = "1.34"
}

variable "private_cluster_enabled" {
  description = "Use a private AKS API endpoint."
  type        = bool
  default     = true
}

variable "node_vm_size" {
  type    = string
  default = "Standard_D2s_v5"
}

variable "node_min_count" {
  type    = number
  default = 2
}

variable "node_max_count" {
  type    = number
  default = 5
}

variable "availability_zones" {
  type    = list(string)
  default = ["1", "2", "3"]
}

variable "sku_tier" {
  description = "AKS control-plane tier. Free is used by the cost-safe lab."
  type        = string
  default     = "Free"

  validation {
    condition     = contains(["Free", "Standard", "Premium"], var.sku_tier)
    error_message = "sku_tier must be Free, Standard, or Premium."
  }
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
