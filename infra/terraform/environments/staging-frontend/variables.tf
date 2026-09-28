variable "aws_profile" {
  description = "Optional local AWS CLI profile."
  type        = string
  default     = null
}

variable "aws_region" {
  description = "AWS region for staging."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID Terraform may manage."
  type        = string
}

variable "environment" {
  description = "Environment managed by this Terraform root."
  type        = string
  default     = "staging"

  validation {
    condition     = var.environment == "staging"
    error_message = "This Terraform root may manage only staging."
  }
}

variable "owner" {
  description = "Person or team responsible for these resources."
  type        = string
}

variable "cost_center" {
  description = "Cost-allocation label."
  type        = string
}