resource "aws_ecs_service" "api" {
  name            = "secure-cloudops-${var.environment}-api"
  cluster         = module.ecs_cluster.cluster_arn
  task_definition = aws_ecs_task_definition.api.arn
  launch_type     = "FARGATE"

  # Define the service without starting a container yet.
  desired_count = 0

  network_configuration {
    subnets          = module.network.public_subnet_ids
    security_groups  = [module.security_groups.security_group_ids["api"]]
    assign_public_ip = true
  }

  tags = {
    Name = "secure-cloudops-${var.environment}-api"
  }
}