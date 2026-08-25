variable "aws_profile" {
  description = "Local AWS CLI profile Terraform should use."
  type        = string
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

variable "document_storage_bucket_name" {
  description = "Existing private S3 bucket that stores redacted extracted document text."
  type        = string
}