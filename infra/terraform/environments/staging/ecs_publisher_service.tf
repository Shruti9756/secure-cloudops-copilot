resource "aws_ecs_service" "publisher" {
  count           = var.runtime_enabled && var.staging_document_queue_backend == "sqs" ? 1 : 0
  name            = "secure-cloudops-${var.environment}-publisher"
  cluster         = module.ecs_cluster.cluster_arn
  task_definition = aws_ecs_task_definition.publisher[0].arn
  launch_type     = "FARGATE"

  # Prepare the service without starting a publisher container.
  desired_count = 0

  network_configuration {
    subnets          = module.network.public_subnet_ids
    security_groups  = [module.security_groups.security_group_ids["publisher"]]
    assign_public_ip = true
  }

  depends_on = [module.security_groups]

  tags = {
    Name = "secure-cloudops-${var.environment}-publisher"
  }
}