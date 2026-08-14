mock_provider "aws" {
  mock_data "aws_partition" {
    defaults = {
      partition = "aws"
    }
  }
}

run "private_multi_az_foundation" {
  command = plan

  variables {
    name                 = "sentinel-dev"
    availability_zones   = ["us-east-1a", "us-east-1b"]
    private_subnet_cidrs = ["10.40.0.0/20", "10.40.16.0/20"]
    public_subnet_cidrs  = ["10.40.128.0/24", "10.40.129.0/24"]
  }

  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_private_access && !aws_eks_cluster.this.vpc_config[0].endpoint_public_access
    error_message = "EKS API must be private by default."
  }

  assert {
    condition     = length(aws_subnet.private) == 2 && length(aws_subnet.public) == 2
    error_message = "The foundation must create public and private subnets across two AZs."
  }

  assert {
    condition     = length(aws_nat_gateway.this) == 0
    error_message = "Cost-safe plans must not create NAT gateways unless explicitly enabled."
  }

  assert {
    condition     = aws_kms_key.eks.enable_key_rotation
    error_message = "EKS secrets and logs must use a rotating KMS key."
  }

  assert {
    condition     = length(aws_eks_cluster.this.enabled_cluster_log_types) == 5
    error_message = "All EKS control-plane log categories must be enabled."
  }
}

run "public_endpoint_requires_explicit_cidrs" {
  command = plan

  variables {
    name                   = "sentinel-dev"
    availability_zones     = ["us-east-1a", "us-east-1b"]
    private_subnet_cidrs   = ["10.40.0.0/20", "10.40.16.0/20"]
    public_subnet_cidrs    = ["10.40.128.0/24", "10.40.129.0/24"]
    endpoint_public_access = true
  }

  expect_failures = [var.public_access_cidrs]
}
