data "aws_iam_policy_document" "publisher_secrets_read" {
  count = var.runtime_enabled && var.staging_document_queue_backend == "sqs" ? 1 : 0

  statement {
    sid       = "ReadPublisherDatabasePassword"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.api_database_password.arn]
  }
}

resource "aws_iam_role_policy" "publisher_secrets_read" {
  count = var.runtime_enabled && var.staging_document_queue_backend == "sqs" ? 1 : 0

  name   = "secure-cloudops-${var.environment}-publisher-db-secret-read"
  role   = module.ecs_roles.execution_role_names["publisher"]
  policy = data.aws_iam_policy_document.publisher_secrets_read[0].json
}