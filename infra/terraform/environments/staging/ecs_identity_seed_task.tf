data "aws_iam_policy_document" "identity_seed_trust" {
  statement {
    sid     = "AllowEcsTasks"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:*"]
    }
  }
}

resource "aws_cloudwatch_log_group" "identity_seed" {
  count             = var.runtime_enabled ? 1 : 0
  name              = "/ecs/secure-cloudops-${var.environment}/identity-seed"
  retention_in_days = 7
}

resource "aws_iam_role" "identity_seed_execution" {
  count              = var.runtime_enabled ? 1 : 0
  name               = "secure-cloudops-${var.environment}-identity-seed-execution"
  assume_role_policy = data.aws_iam_policy_document.identity_seed_trust.json
}

data "aws_iam_policy_document" "identity_seed_execution" {
  count = var.runtime_enabled ? 1 : 0

  statement {
    sid       = "GetEcrPullToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "PullOnlyApiImage"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [module.container_registry.repository_arns["api"]]
  }

  statement {
    sid = "WriteOnlyIdentitySeedLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.identity_seed[0].arn}:log-stream:*"]
  }

  statement {
    sid       = "ReadOnlyApplicationDatabasePassword"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.api_database_password.arn]
  }
}

resource "aws_iam_role_policy" "identity_seed_execution" {
  count  = var.runtime_enabled ? 1 : 0
  name   = "secure-cloudops-${var.environment}-identity-seed-execution"
  role   = aws_iam_role.identity_seed_execution[0].name
  policy = data.aws_iam_policy_document.identity_seed_execution[0].json
}

resource "aws_ecs_task_definition" "identity_seed" {
  count                    = var.runtime_enabled ? 1 : 0
  family                   = "secure-cloudops-${var.environment}-identity-seed"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.identity_seed_execution[0].arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name                   = "identity-seed"
    image                  = "${module.container_registry.repository_urls["api"]}:${local.staging_api_image_tag}"
    essential              = true
    user                   = "app"
    readonlyRootFilesystem = true

    # Missing --subject intentionally prevents an accidental seed.
    command = ["python", "-m", "app.db.staging_identity"]

    linuxParameters = {
      capabilities = {
        drop = ["ALL"]
      }
    }

    environment = [
      { name = "APP_ENV", value = "staging" },
      { name = "STAGING_IDENTITY_SEED_CONFIRMATION", value = "synthetic-staging-only" },
      { name = "IDENTITY_PROVIDER", value = "cognito" },
      { name = "COGNITO_ISSUER", value = var.staging_cognito_issuer },
      { name = "DATABASE_HOST", value = aws_db_instance.staging[0].address },
      { name = "DATABASE_PORT", value = tostring(aws_db_instance.staging[0].port) },
      { name = "DATABASE_NAME", value = aws_db_instance.staging[0].db_name },
      { name = "DATABASE_USERNAME", value = "securecloudops_app" },
    ]

    secrets = [{
      name      = "DATABASE_PASSWORD"
      valueFrom = aws_secretsmanager_secret.api_database_password.arn
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.identity_seed[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "identity-seed"
      }
    }
  }])

  depends_on = [
    aws_iam_role_policy.identity_seed_execution,
    aws_secretsmanager_secret_version.api_database_password,
  ]

  lifecycle {
    precondition {
      condition = (
        var.aws_account_id == "291667884598"
        && var.aws_region == "us-east-1"
        && var.staging_cognito_issuer == "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_cgRH4viJI"
      )
      error_message = "The identity seed is restricted to the approved staging account, region, and Cognito pool."
    }
  }
}