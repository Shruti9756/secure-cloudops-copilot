terraform {
  # Keep the project compatible with the Terraform CLI you just installed.
  required_version = ">= 1.15.0, < 2.0.0"

  required_providers {
    aws = {
      # HashiCorp's official AWS provider.
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}