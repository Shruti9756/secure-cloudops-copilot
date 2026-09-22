variable "name_prefix" {
  description = "Prefix used for network resource names."
  type        = string

  validation {
    condition     = length(trimspace(var.name_prefix)) > 0
    error_message = "name_prefix must not be empty."
  }
}

variable "vpc_cidr" {
  description = "IPv4 CIDR range assigned to the VPC."
  type        = string

  validation {
    condition     = try(cidrnetmask(var.vpc_cidr), "") == "255.255.0.0"
    error_message = "The network VPC CIDR must be a valid IPv4 /16 range."
  }
}

variable "availability_zones" {
  description = "Exactly two Availability Zones used for public and private subnets."
  type        = list(string)

  validation {
    condition = (
      length(var.availability_zones) == 2
      && length(distinct(var.availability_zones)) == 2
      && alltrue([
        for availability_zone in var.availability_zones :
        length(trimspace(availability_zone)) > 0
      ])
    )
    error_message = "availability_zones must contain exactly two distinct non-empty zones."
  }
}