output "terraform_target" {
  description = "Safe summary of the intended Terraform target. No credentials are included."

  value = {
    aws_region                   = var.aws_region
    environment                  = var.environment
    document_storage_bucket_name = var.document_storage_bucket_name
  }
}

output "document_storage_bucket_id" {
  description = "Name of the imported private S3 document-storage bucket."
  value       = aws_s3_bucket.redacted_document_storage.id
}