variable "staging_api_connection_mode" {
  description = "CloudFront API connection: disabled, prepared (detached), or attached."
  type        = string
  default     = "disabled"
  nullable    = false

  validation {
    condition     = contains(["disabled", "prepared", "attached"], var.staging_api_connection_mode)
    error_message = "Use disabled, prepared, or attached for staging_api_connection_mode."
  }
}

variable "staging_api_alb_arn" {
  description = "ARN of the active staging API ALB; leave blank while disabled."
  type        = string
  default     = ""
  nullable    = false
}

variable "staging_api_alb_dns_name" {
  description = "DNS name of the same staging API ALB, without a scheme or path."
  type        = string
  default     = ""
  nullable    = false
}

resource "aws_cloudfront_vpc_origin" "api" {
  count = var.staging_api_connection_mode != "disabled" ? 1 : 0

  vpc_origin_endpoint_config {
    name                   = "secure-cloudops-${var.environment}-api"
    arn                    = var.staging_api_alb_arn
    http_port              = 80
    https_port             = 443
    origin_protocol_policy = "http-only"

    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }

  lifecycle {
    precondition {
      condition = can(regex(
        "^arn:aws:elasticloadbalancing:${var.aws_region}:${var.aws_account_id}:loadbalancer/app/secure-cloudops-${var.environment}-api/[A-Za-z0-9]+$",
        var.staging_api_alb_arn,
      ))
      error_message = "Set staging_api_alb_arn to the real staging API ALB ARN in this account and region before preparing or attaching."
    }

    precondition {
      condition = can(regex(
        "^internal-secure-cloudops-${var.environment}-api-[A-Za-z0-9-]+\\.${var.aws_region}\\.elb\\.amazonaws\\.com$",
        var.staging_api_alb_dns_name,
      ))
      error_message = "Set staging_api_alb_dns_name to the internal DNS name of that same active ALB, without https:// or a path."
    }
  }
}

output "staging_api_vpc_origin_id" {
  description = "Private API connection ID; absent while disabled."
  value       = try(aws_cloudfront_vpc_origin.api[0].id, null)
}