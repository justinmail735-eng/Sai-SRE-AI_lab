variable "name" {
  description = "Short environment name used for resource naming."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.name))
    error_message = "name must be a lowercase DNS-style value between 3 and 31 characters."
  }
}

variable "vpc_cidr" {
  description = "IPv4 CIDR for the workload VPC."
  type        = string
  default     = "10.40.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 1))
    error_message = "vpc_cidr must be a valid IPv4 CIDR."
  }
}

variable "availability_zones" {
  description = "Availability zones used by public and private subnets."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "at least two availability zones are required."
  }
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDRs, one per availability zone."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_cidrs) >= 2 && alltrue([for cidr in var.private_subnet_cidrs : can(cidrhost(cidr, 1))])
    error_message = "at least two valid private subnet CIDRs are required."
  }
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs, one per availability zone."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) >= 2 && alltrue([for cidr in var.public_subnet_cidrs : can(cidrhost(cidr, 1))])
    error_message = "at least two valid public subnet CIDRs are required."
  }
}

variable "enable_nat_gateway" {
  description = "Create NAT gateways for private-node egress. Disabled in cost-safe plan examples."
  type        = bool
  default     = false
}

variable "single_nat_gateway" {
  description = "Use one NAT gateway instead of one per AZ. Suitable for non-production labs only."
  type        = bool
  default     = false
}

variable "kubernetes_version" {
  description = "EKS control-plane Kubernetes version."
  type        = string
  default     = "1.34"
}

variable "endpoint_public_access" {
  description = "Expose the Kubernetes API publicly. Disabled by default."
  type        = bool
  default     = false
}

variable "public_access_cidrs" {
  description = "CIDRs allowed to reach the public Kubernetes API when enabled."
  type        = list(string)
  default     = []

  validation {
    condition     = !var.endpoint_public_access || length(var.public_access_cidrs) > 0
    error_message = "public_access_cidrs must be explicitly set when endpoint_public_access is true."
  }
}

variable "node_instance_types" {
  description = "Allowed managed-node instance types."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 4
}

variable "log_retention_days" {
  description = "CloudWatch retention for cluster and flow logs."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Additional resource tags."
  type        = map(string)
  default     = {}
}
