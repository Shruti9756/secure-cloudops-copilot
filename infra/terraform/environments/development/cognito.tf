# A Cognito User Pool is AWS's managed user directory.
# It handles sign-in, password reset, email verification, and MFA.
resource "aws_cognito_user_pool" "secure_cloudops" {
  name = "secure-cloudops-copilot-${var.environment}"

  # State the existing default explicitly: managed login requires Essentials.
  user_pool_tier = "ESSENTIALS"

  # Prevent accidental deletion of the authentication directory.
  deletion_protection = "ACTIVE"

  # Users sign in using their email address.
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  username_configuration {
    # Treat SHRUTI@example.com and shruti@example.com as the same username.
    case_sensitive = false
  }

  # Public self-registration is disabled; an administrator creates users.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  # Authenticator-app MFA is available, but not mandatory during local development.
  mfa_configuration = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  # Require a reasonably strong initial password policy.
  password_policy {
    minimum_length                   = 14
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 3
  }

  # Email is the only account-recovery option in this local project.
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

# This is a public browser client. It deliberately has no secret because
# frontend code is visible to users. The frontend will later use PKCE.
resource "aws_cognito_user_pool_client" "web" {
  name         = "secure-cloudops-web-${var.environment}"
  user_pool_id = aws_cognito_user_pool.secure_cloudops.id

  generate_secret               = false
  supported_identity_providers  = ["COGNITO"]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  # Use the safer OAuth authorization-code flow.
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]

  # The Next.js callback route will be implemented next.
  callback_urls = ["http://localhost:3000/auth/callback"]
  logout_urls   = ["http://localhost:3000/"]

  # Keep browser tokens short-lived in development.
  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 1

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

# This AWS-owned prefix becomes the login website address.
# No domain purchase, DNS, or certificate is needed.
resource "aws_cognito_user_pool_domain" "secure_cloudops" {
  domain                = "secure-cloudops-copilot-${var.environment}-${var.aws_account_id}"
  user_pool_id          = aws_cognito_user_pool.secure_cloudops.id
  managed_login_version = 2
}

# Apply Cognito's maintained default styling so this Terraform-created
# app client can use the managed sign-in pages.
resource "aws_cognito_managed_login_branding" "web" {
  client_id    = aws_cognito_user_pool_client.web.id
  user_pool_id = aws_cognito_user_pool.secure_cloudops.id

  use_cognito_provided_values = true
}