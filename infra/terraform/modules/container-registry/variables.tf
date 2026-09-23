variable "name_prefix" {
  description = "Environment-specific prefix for ECR repository names."
  type        = string
}

variable "image_retention_count" {
  description = "Maximum number of images retained in each repository."
  type        = number
  default     = 10

  validation {
    condition = (
      var.image_retention_count >= 1 &&
      floor(var.image_retention_count) == var.image_retention_count
    )
    error_message = "image_retention_count must be a positive whole number."
  }
}