provider "aws" {
  # These values come from a local .tfvars file, never from hard-coded credentials.
  profile = var.aws_profile
  region  = var.aws_region

  # Refuse to run if the selected profile belongs to a different AWS account.
  allowed_account_ids = [var.aws_account_id]

  # Every future Terraform-managed AWS resource receives these common tags.
  default_tags {
    tags = {
      Project     = "SecureCloudOpsCopilot"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}