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

output "cognito_user_pool_id" {
  description = "Public ID of the SecureCloudOps Cognito User Pool."
  value       = aws_cognito_user_pool.secure_cloudops.id
}

output "cognito_web_client_id" {
  description = "Public ID for the browser-based SecureCloudOps app client."
  value       = aws_cognito_user_pool_client.web.id
}

output "cognito_issuer" {
  description = "JWT issuer URL the API will verify."

  value = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.secure_cloudops.id}"
}

output "cognito_managed_login_base_url" {
  description = "AWS-hosted Cognito sign-in website base URL."

  value = "https://${aws_cognito_user_pool_domain.secure_cloudops.domain}.auth.${var.aws_region}.amazoncognito.com"
}