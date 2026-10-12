resource "aws_ecs_task_definition" "publisher" {
  count                    = var.runtime_enabled && var.staging_document_queue_backend == "sqs" ? 1 : 0
  family                   = "secure-cloudops-${var.environment}-publisher"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "1024"
  execution_role_arn       = module.ecs_roles.execution_role_arns["publisher"]
  task_role_arn            = module.ecs_roles.task_role_arns["publisher"]

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "publisher"
    image     = "${module.container_registry.repository_urls["api"]}:${local.staging_api_image_tag}"
    essential = true
    command   = ["python", "-m", "app.document_outbox_publisher"]

    environment = [
      { name = "AWS_REGION", value = var.aws_region },
      { name = "DOCUMENT_QUEUE_BACKEND", value = var.staging_document_queue_backend },
      { name = "DOCUMENT_QUEUE_SQS_URL", value = aws_sqs_queue.document_processing.id },
      { name = "DOCUMENT_OUTBOX_POLL_INTERVAL_SECONDS", value = "5" },
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
        "awslogs-group"         = module.ecs_cluster.log_group_names["publisher"]
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "publisher"
      }
    }
  }])

  depends_on = [
    module.ecs_roles,
    aws_iam_role_policy.document_queue_publish,
    aws_iam_role_policy.publisher_secrets_read,
    aws_secretsmanager_secret_version.api_database_password,
  ]

  tags = {
    Name = "secure-cloudops-${var.environment}-publisher"
  }
}