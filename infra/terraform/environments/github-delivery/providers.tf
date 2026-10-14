provider "aws" {
  # Local commands use AWS_PROFILE; no access keys belong in this configuration.
  region              = "us-east-1"
  allowed_account_ids = ["291667884598"]

  default_tags {
    tags = {
      Project     = "SecureCloudOpsCopilot"
      Environment = "shared"
      Owner       = "Shruti"
      CostCenter  = "personal-learning"
      ManagedBy   = "Terraform"
    }
  }
}