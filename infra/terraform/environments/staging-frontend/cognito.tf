# Persistent staging sign-in configuration; independent of runtime_enabled.
locals {
  staging_frontend_origin = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

resource "aws_cognito_user_pool" "staging" {
  name                = "secure-cloudops-copilot-${var.environment}"
  user_pool_tier      = "ESSENTIALS"
  deletion_protection = "ACTIVE"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  username_configuration {
    case_sensitive = false
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  mfa_configuration = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  password_policy {
    minimum_length                   = 14
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 3
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

# Browser client: no secret, authorization-code flow with the app's existing PKCE.
resource "aws_cognito_user_pool_client" "staging_web" {
  name         = "secure-cloudops-web-${var.environment}"
  user_pool_id = aws_cognito_user_pool.staging.id

  generate_secret               = false
  supported_identity_providers  = ["COGNITO"]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]

  callback_urls = ["${local.staging_frontend_origin}/auth/callback.html"]
  logout_urls   = ["${local.staging_frontend_origin}/"]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 1

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

resource "aws_cognito_user_pool_domain" "staging" {
  domain                = "secure-cloudops-copilot-${var.environment}-${var.aws_account_id}"
  user_pool_id          = aws_cognito_user_pool.staging.id
  managed_login_version = 2
}

resource "aws_cognito_managed_login_branding" "staging_web" {
  client_id    = aws_cognito_user_pool_client.staging_web.id
  user_pool_id = aws_cognito_user_pool.staging.id

  use_cognito_provided_values = true

  depends_on = [aws_cognito_user_pool_domain.staging]
}
