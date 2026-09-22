variable "aws_profile" {
  description = "Optional local AWS CLI profile. Leave null when using workload or GitHub OIDC credentials."
  type        = string
  default     = null
}

variable "aws_region" {
  description = "AWS region for the staging environment."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID Terraform is allowed to manage."
  type        = string
}

variable "environment" {
  description = "Deployment environment represented by this Terraform root."
  type        = string
  default     = "staging"

  validation {
    condition     = var.environment == "staging"
    error_message = "This Terraform root may manage only the staging environment."
  }
}

variable "owner" {
  description = "Person or team responsible for staging resources."
  type        = string

  validation {
    condition     = length(trimspace(var.owner)) > 0
    error_message = "owner must not be empty."
  }
}

variable "cost_center" {
  description = "Cost-allocation label for staging resources."
  type        = string

  validation {
    condition     = length(trimspace(var.cost_center)) > 0
    error_message = "cost_center must not be empty."
  }
}

variable "network_vpc_cidr" {
  description = "IPv4 CIDR assigned to this environment's VPC."
  type        = string

  validation {
    condition     = try(cidrnetmask(var.network_vpc_cidr), "") == "255.255.0.0"
    error_message = "The network VPC CIDR must be a valid IPv4 /16 range."
  }
}

variable "network_availability_zones" {
  description = "Two Availability Zones used by this environment."
  type        = list(string)

  validation {
    condition = (
      length(var.network_availability_zones) == 2
      && length(distinct(var.network_availability_zones)) == 2
    )
    error_message = "network_availability_zones must contain exactly two distinct zones."
  }
}