resource "aws_ecs_task_definition" "worker" {
  count                    = var.runtime_enabled ? 1 : 0
  family                   = "secure-cloudops-${var.environment}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "1024"
  execution_role_arn       = module.ecs_roles.execution_role_arns["worker"]
  task_role_arn            = module.ecs_roles.task_role_arns["worker"]

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "worker"
    image     = "${module.container_registry.repository_urls["api"]}:${local.staging_api_image_tag}"
    essential = true
    command   = ["python", "-m", "app.worker"]

    environment = [
      { name = "APP_ENV", value = "staging" },
      { name = "AWS_REGION", value = var.aws_region },
      { name = "DATABASE_HOST", value = aws_db_instance.staging[0].address },
      { name = "DATABASE_PORT", value = tostring(aws_db_instance.staging[0].port) },
      { name = "DATABASE_NAME", value = aws_db_instance.staging[0].db_name },
      { name = "DATABASE_USERNAME", value = "securecloudops_app" },
      { name = "REDIS_HOST", value = one(data.aws_elasticache_cluster.staging_node[0].cache_nodes).address },
      { name = "REDIS_PORT", value = tostring(one(data.aws_elasticache_cluster.staging_node[0].cache_nodes).port) },
      { name = "DOCUMENT_PROCESSOR_POLL_INTERVAL_SECONDS", value = "5" },
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

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = module.ecs_cluster.log_group_names["worker"]
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "worker"
      }
    }
  }])

  depends_on = [
    aws_iam_role_policy.worker_secrets_read,
    aws_secretsmanager_secret_version.api_database_password,
    aws_secretsmanager_secret_version.cache_auth,
  ]

  tags = {
    Name = "secure-cloudops-${var.environment}-worker"
  }
}