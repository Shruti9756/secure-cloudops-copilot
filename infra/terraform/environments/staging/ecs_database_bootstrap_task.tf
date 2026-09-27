locals {
  bootstrap_master_secret_arn = one(aws_db_instance.staging.master_user_secret).secret_arn
}

data "aws_iam_policy_document" "database_bootstrap_trust" {
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

resource "aws_iam_role" "database_bootstrap_execution" {
  name               = "secure-cloudops-${var.environment}-db-bootstrap-execution"
  assume_role_policy = data.aws_iam_policy_document.database_bootstrap_trust.json
}

resource "aws_iam_role_policy_attachment" "database_bootstrap_execution" {
  role       = aws_iam_role.database_bootstrap_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "database_bootstrap_secrets" {
  statement {
    sid     = "ReadBootstrapDatabasePasswords"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      local.bootstrap_master_secret_arn,
      aws_secretsmanager_secret.api_database_password.arn,
    ]
  }
}

resource "aws_iam_role_policy" "database_bootstrap_secrets" {
  name   = "secure-cloudops-${var.environment}-db-bootstrap-secrets"
  role   = aws_iam_role.database_bootstrap_execution.name
  policy = data.aws_iam_policy_document.database_bootstrap_secrets.json
}

resource "aws_cloudwatch_log_group" "database_bootstrap" {
  name              = "/ecs/secure-cloudops-${var.environment}/database-bootstrap"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "database_bootstrap" {
  family                   = "secure-cloudops-${var.environment}-database-bootstrap"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.database_bootstrap_execution.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "database-bootstrap"
    image     = "${module.container_registry.repository_urls["api"]}:${local.staging_api_image_tag}"
    essential = true
    command   = ["python", "-m", "app.db.bootstrap"]

    environment = [
      { name = "APP_ENV", value = "staging" },
      { name = "DATABASE_HOST", value = aws_db_instance.staging.address },
      { name = "DATABASE_PORT", value = tostring(aws_db_instance.staging.port) },
      { name = "DATABASE_NAME", value = aws_db_instance.staging.db_name },
      { name = "DATABASE_ADMIN_USERNAME", value = aws_db_instance.staging.username },
      { name = "DATABASE_APP_USERNAME", value = "securecloudops_app" },
    ]

    secrets = [
      {
        name      = "DATABASE_ADMIN_PASSWORD"
        valueFrom = "${local.bootstrap_master_secret_arn}:password::"
      },
      {
        name      = "DATABASE_APP_PASSWORD"
        valueFrom = aws_secretsmanager_secret.api_database_password.arn
      },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.database_bootstrap.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "database-bootstrap"
      }
    }
  }])

  depends_on = [
    aws_iam_role_policy_attachment.database_bootstrap_execution,
    aws_iam_role_policy.database_bootstrap_secrets,
    aws_secretsmanager_secret_version.api_database_password,
  ]
}