variable "aws_profile" {
  description = "Optional local AWS CLI profile. Leave null when Terraform uses workload or GitHub OIDC credentials."
  type        = string
  default     = null
}

variable "aws_region" {
  description = "AWS region where project infrastructure exists."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID Terraform is allowed to manage."
  type        = string
}

variable "environment" {
  description = "Deployment environment label used for resource tags."
  type        = string
  default     = "development"
}

variable "owner" {
  description = "Person or team responsible for these AWS resources."
  type        = string

  validation {
    condition     = length(trimspace(var.owner)) > 0
    error_message = "owner must not be empty."
  }
}

variable "cost_center" {
  description = "Cost-allocation label for these AWS resources."
  type        = string

  validation {
    condition     = length(trimspace(var.cost_center)) > 0
    error_message = "cost_center must not be empty."
  }
}

variable "monthly_budget_usd" {
  description = "Account-wide monthly AWS cost budget in US dollars."
  type        = number
  default     = 5

  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "monthly_budget_usd must be greater than zero."
  }
}

variable "budget_alert_email" {
  description = "Email address that receives AWS Budget notifications."
  type        = string
  sensitive   = true
}

variable "document_storage_bucket_name" {
  description = "Existing private S3 bucket that stores redacted extracted document text."
  type        = string
}