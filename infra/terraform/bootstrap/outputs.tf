output "terraform_state_bucket_name" {
  description = "Private S3 bucket used for remote Terraform state."
  value       = aws_s3_bucket.terraform_state.id
}

output "development_state_key" {
  description = "Planned S3 object key for the existing development state."
  value       = "states/development/platform.tfstate"
}