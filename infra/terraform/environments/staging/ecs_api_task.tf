locals {
  staging_api_image_tag = "50ae30a0e4aa8ae1e1fa1c419c4f49d7fd21e382"
}

resource "aws_ecs_task_definition" "api" {
  count                    = var.runtime_enabled ? 1 : 0
  family                   = "secure-cloudops-${var.environment}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "1024"
  execution_role_arn       = module.ecs_roles.execution_role_arns["api"]
  task_role_arn            = module.ecs_roles.task_role_arns["api"]

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "api"
    image     = "${module.container_registry.repository_urls["api"]}:${local.staging_api_image_tag}"
    essential = true
    environment = [
      { name = "APP_ENV", value = "staging" },
      { name = "IDENTITY_PROVIDER", value = "cognito" },
      { name = "COGNITO_ISSUER", value = var.staging_cognito_issuer },
      { name = "COGNITO_APP_CLIENT_ID", value = var.staging_cognito_app_client_id },
      { name = "DATABASE_HOST", value = aws_db_instance.staging[0].address },
      { name = "DATABASE_PORT", value = tostring(aws_db_instance.staging[0].port) },
      { name = "DATABASE_NAME", value = aws_db_instance.staging[0].db_name },
      { name = "DATABASE_USERNAME", value = "securecloudops_app" },
      { name = "REDIS_HOST", value = one(data.aws_elasticache_cluster.staging_node[0].cache_nodes).address },
      { name = "REDIS_PORT", value = tostring(one(data.aws_elasticache_cluster.staging_node[0].cache_nodes).port) },
    ]
    secrets = [
      {
        name      = "DATABASE_PASSWORD"
        valueFrom = aws_secretsmanager_secret.api_database_password.arn
      },
      {
        name      = "REDIS_PASSWORD"
        valueFrom = aws_secretsmanager_secret.cache_auth_token.arn
      },
    ]
    portMappings = [{
      containerPort = 8000
      hostPort      = 8000
      protocol      = "tcp"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = module.ecs_cluster.log_group_names["api"]
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }
  }])

  tags = {
    Name = "secure-cloudops-${var.environment}-api"
  }
  lifecycle {
    precondition {
      condition = (
        startswith(var.staging_cognito_issuer, "https://cognito-idp.${var.aws_region}.amazonaws.com/")
        && length(var.staging_cognito_issuer) > length("https://cognito-idp.${var.aws_region}.amazonaws.com/")
        && length(trimspace(var.staging_cognito_app_client_id)) > 0
      )
      error_message = "Set the staging Cognito issuer and app client ID before enabling the runtime."
    }
  }
}