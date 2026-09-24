variable "name_prefix" {
  description = "Prefix used for security-group names."
  type        = string

  validation {
    condition     = length(trimspace(var.name_prefix)) > 0
    error_message = "name_prefix must not be empty."
  }
}

variable "vpc_id" {
  description = "VPC where the security groups are created."
  type        = string

  validation {
    condition     = length(trimspace(var.vpc_id)) > 0
    error_message = "vpc_id must not be empty."
  }
}

variable "frontend_port" {
  description = "TCP port used by the frontend container."
  type        = number
  default     = 3000

  validation {
    condition = (
      var.frontend_port >= 1
      && var.frontend_port <= 65535
      && floor(var.frontend_port) == var.frontend_port
    )
    error_message = "frontend_port must be an integer from 1 through 65535."
  }
}

variable "api_port" {
  description = "TCP port used by the API container."
  type        = number
  default     = 8000

  validation {
    condition = (
      var.api_port >= 1
      && var.api_port <= 65535
      && floor(var.api_port) == var.api_port
    )
    error_message = "api_port must be an integer from 1 through 65535."
  }
}

variable "database_port" {
  description = "TCP port used by PostgreSQL."
  type        = number
  default     = 5432

  validation {
    condition = (
      var.database_port >= 1
      && var.database_port <= 65535
      && floor(var.database_port) == var.database_port
    )
    error_message = "database_port must be an integer from 1 through 65535."
  }
}

variable "cache_port" {
  description = "TCP port used by Redis."
  type        = number
  default     = 6379

  validation {
    condition = (
      var.cache_port >= 1
      && var.cache_port <= 65535
      && floor(var.cache_port) == var.cache_port
    )
    error_message = "cache_port must be an integer from 1 through 65535."
  }
}

variable "allow_public_https_egress" {
  description = "Allow application tasks outbound HTTPS for public-subnet staging."
  type        = bool
  default     = false
}
