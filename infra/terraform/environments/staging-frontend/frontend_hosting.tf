resource "aws_s3_bucket" "frontend" {
  bucket        = "secure-cloudops-${var.environment}-web-${var.aws_account_id}-${var.aws_region}"
  force_destroy = false

  tags = {
    Purpose = "static-frontend"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "secure-cloudops-${var.environment}-web"
  description                       = "CloudFront access to the private staging frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "SecureCloudOps ${var.environment} static frontend"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  wait_for_deployment = true

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "frontend-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  dynamic "origin" {
    for_each = var.staging_api_connection_mode == "attached" ? [1] : []

    content {
      domain_name = var.staging_api_alb_dns_name
      origin_id   = "api-private-alb"

      vpc_origin_config {
        vpc_origin_id            = aws_cloudfront_vpc_origin.api[0].id
        origin_read_timeout      = 60
        origin_keepalive_timeout = 5
      }
    }
  }

  default_cache_behavior {
    target_origin_id       = "frontend-s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # AWS-managed CachingOptimized policy.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  dynamic "ordered_cache_behavior" {
    for_each = var.staging_api_connection_mode == "attached" ? [1] : []

    content {
      path_pattern           = "/api/*"
      target_origin_id       = "api-private-alb"
      viewer_protocol_policy = "https-only"
      allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
      cached_methods         = ["GET", "HEAD"]
      compress               = true

      # AWS-managed CachingDisabled: do not cache authenticated API responses.
      cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"

      # Forward authorization, workspace headers, cookies, and query strings.
      origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
    }
  }

  dynamic "custom_error_response" {
    for_each = var.staging_api_connection_mode == "attached" ? toset([
      400, 403, 404, 405, 414, 500, 501, 502, 503, 504,
    ]) : toset([])

    content {
      error_code            = custom_error_response.value
      error_caching_min_ttl = 0
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  depends_on = [
    aws_s3_bucket_public_access_block.frontend,
    aws_s3_bucket_ownership_controls.frontend,
  ]
}

data "aws_iam_policy_document" "frontend_cloudfront_read" {
  statement {
    sid       = "AllowThisCloudFrontDistributionToRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_cloudfront_read.json
}