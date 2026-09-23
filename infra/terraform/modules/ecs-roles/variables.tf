variable "name_prefix" {
  description = "Prefix for staging ECS role names."
  type        = string
}

variable "aws_region" {
  description = "Region in which ECS tasks will run."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account allowed to run these ECS tasks."
  type        = string
}