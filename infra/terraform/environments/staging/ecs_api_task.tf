locals {
  staging_api_image_tag = "c927ad5fc9769c5e9146e2218bd7d027a9581bc4"
}

resource "aws_ecs_task_definition" "api" {
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
}