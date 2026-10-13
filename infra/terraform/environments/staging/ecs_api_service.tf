resource "aws_ecs_service" "api" {
  count           = var.runtime_enabled ? 1 : 0
  name            = "secure-cloudops-${var.environment}-api"
  cluster         = module.ecs_cluster.cluster_arn
  task_definition = aws_ecs_task_definition.api[0].arn
  launch_type     = "FARGATE"

  # Register the service without starting a container.
  desired_count                     = 0
  health_check_grace_period_seconds = 60

  load_balancer {
    target_group_arn = aws_lb_target_group.api[0].arn
    container_name   = "api"
    container_port   = 8000
  }

  network_configuration {
    subnets          = module.network.public_subnet_ids
    security_groups  = [module.security_groups.security_group_ids["api"]]
    assign_public_ip = true
  }

  tags = {
    Name = "secure-cloudops-${var.environment}-api"
  }

  depends_on = [
    aws_lb_listener.api_http,
    module.security_groups,
  ]
}