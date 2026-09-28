output "frontend_hosting" {
  description = "Private bucket and AWS-provided HTTPS address for the staging frontend."

  value = {
    bucket_name     = aws_s3_bucket.frontend.id
    distribution_id = aws_cloudfront_distribution.frontend.id
    https_url       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
  }
}