output "frontend_hosting" {
  description = "Private bucket and AWS-provided HTTPS address for the staging frontend."

  value = {
    bucket_name     = aws_s3_bucket.frontend.id
    distribution_id = aws_cloudfront_distribution.frontend.id
    https_url       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
  }
}

output "staging_identity" {
  description = "Public identifiers and URLs for the dedicated staging browser sign-in."

  value = {
    user_pool_id           = aws_cognito_user_pool.staging.id
    issuer                 = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.staging.id}"
    app_client_id          = aws_cognito_user_pool_client.staging_web.id
    managed_login_base_url = "https://${aws_cognito_user_pool_domain.staging.domain}.auth.${var.aws_region}.amazoncognito.com"
    redirect_uri           = "${local.staging_frontend_origin}/auth/callback.html"
    logout_uri             = "${local.staging_frontend_origin}/"
  }
}
