resource "aws_ecs_service" "worker" {
  count           = var.runtime_enabled ? 1 : 0
  name            = "secure-cloudops-${var.environment}-worker"
  cluster         = module.ecs_cluster.cluster_arn
  task_definition = aws_ecs_task_definition.worker[0].arn
  launch_type     = "FARGATE"

  # Register the service without starting a worker container.
  desired_count = 0

  network_configuration {
    subnets          = module.network.public_subnet_ids
    security_groups  = [module.security_groups.security_group_ids["worker"]]
    assign_public_ip = true
  }

  tags = {
    Name = "secure-cloudops-${var.environment}-worker"
  }
}