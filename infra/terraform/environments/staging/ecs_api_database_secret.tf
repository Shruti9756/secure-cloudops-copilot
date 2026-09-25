resource "aws_secretsmanager_secret" "api_database_password" {
  name                    = "secure-cloudops-${var.environment}/api/database-password"
  description             = "Password for the staging API application database role."
  recovery_window_in_days = 7
}

data "aws_iam_policy_document" "api_database_password_read" {
  statement {
    sid       = "ReadApiDatabasePassword"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.api_database_password.arn]
  }
}

resource "aws_iam_role_policy" "api_database_password_read" {
  name   = "secure-cloudops-${var.environment}-api-db-secret-read"
  role   = module.ecs_roles.execution_role_names["api"]
  policy = data.aws_iam_policy_document.api_database_password_read.json
}