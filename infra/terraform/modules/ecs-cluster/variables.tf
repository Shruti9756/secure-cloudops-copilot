variable "name_prefix" {
  description = "Environment-specific prefix for ECS resources."
  type        = string
}

variable "log_retention_days" {
  description = "Days to retain container logs."
  type        = number
  default     = 7

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30], var.log_retention_days)
    error_message = "log_retention_days must be 1, 3, 5, 7, 14, or 30."
  }
}