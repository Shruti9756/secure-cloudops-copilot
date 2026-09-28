provider "aws" {
  profile = var.aws_profile
  region  = var.aws_region

  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Project     = "SecureCloudOpsCopilot"
      Environment = var.environment
      Owner       = var.owner
      CostCenter  = var.cost_center
      ManagedBy   = "Terraform"
    }
  }
}