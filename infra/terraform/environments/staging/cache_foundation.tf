resource "aws_elasticache_subnet_group" "staging" {
  name       = "secure-cloudops-${var.environment}-cache-subnets"
  subnet_ids = module.network.private_subnet_ids
}

resource "aws_secretsmanager_secret" "cache_auth_token" {
  name                    = "secure-cloudops-${var.environment}/cache/auth-token"
  description             = "AUTH token shared by the staging API and worker."
  recovery_window_in_days = 7
}

data "aws_iam_policy_document" "api_cache_auth_read" {
  statement {
    sid       = "ReadStagingCacheAuthToken"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.cache_auth_token.arn]
  }
}

resource "aws_iam_role_policy" "api_cache_auth_read" {
  name   = "secure-cloudops-${var.environment}-api-cache-auth-read"
  role   = module.ecs_roles.execution_role_names["api"]
  policy = data.aws_iam_policy_document.api_cache_auth_read.json
}