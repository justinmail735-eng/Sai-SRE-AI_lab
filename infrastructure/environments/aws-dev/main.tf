module "platform" {
  source = "../../modules/aws-eks"

  name                 = "sentinelsre-dev"
  availability_zones   = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnet_cidrs = ["10.40.0.0/20", "10.40.16.0/20"]
  public_subnet_cidrs  = ["10.40.128.0/24", "10.40.129.0/24"]

  # The demo plan avoids hourly NAT charges. Enable this only when nodes need
  # internet egress and the cost/availability trade-off has been reviewed.
  enable_nat_gateway = false

  tags = {
    Owner      = "platform-sre"
    CostCenter = "sentinelsre-lab"
  }
}
