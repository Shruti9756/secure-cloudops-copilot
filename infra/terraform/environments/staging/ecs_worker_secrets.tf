data "aws_iam_policy_document" "worker_secrets_read" {
  count = var.runtime_enabled ? 1 : 0

  statement {
    sid     = "ReadWorkerDatabaseAndCachePasswords"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.api_database_password.arn,
      aws_secretsmanager_secret.cache_auth_token.arn,
    ]
  }
}

resource "aws_iam_role_policy" "worker_secrets_read" {
  count = var.runtime_enabled ? 1 : 0

  name   = "secure-cloudops-${var.environment}-worker-secrets-read"
  role   = module.ecs_roles.execution_role_names["worker"]
  policy = data.aws_iam_policy_document.worker_secrets_read[0].json
}