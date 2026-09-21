variable "aws_profile" {
  description = "Optional local AWS CLI profile. Leave null when using workload or GitHub OIDC credentials."
  type        = string
  default     = null
}

variable "aws_region" {
  description = "AWS region containing the Terraform state bucket."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID Terraform is allowed to manage."
  type        = string
}

variable "owner" {
  description = "Person or team responsible for the Terraform state infrastructure."
  type        = string

  validation {
    condition     = length(trimspace(var.owner)) > 0
    error_message = "owner must not be empty."
  }
}

variable "cost_center" {
  description = "Cost-allocation label for the Terraform state infrastructure."
  type        = string

  validation {
    condition     = length(trimspace(var.cost_center)) > 0
    error_message = "cost_center must not be empty."
  }
}

variable "terraform_state_bucket_name" {
  description = "Globally unique private S3 bucket used for remote Terraform state."
  type        = string
}