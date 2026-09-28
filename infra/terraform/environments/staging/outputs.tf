output "network_summary" {
  description = "Non-sensitive IDs for the staging network."

  value = {
    vpc_id             = module.network.vpc_id
    availability_zones = module.network.availability_zones
    public_subnet_ids  = module.network.public_subnet_ids
    private_subnet_ids = module.network.private_subnet_ids
    security_group_ids = module.security_groups.security_group_ids
  }
}

output "container_repository_urls" {
  description = "Private ECR URLs for application images."
  value       = module.container_registry.repository_urls
}

output "ecs_role_arns" {
  description = "IAM role ARNs reserved for staging ECS services."

  value = {
    execution = module.ecs_roles.execution_role_arns
    task      = module.ecs_roles.task_role_arns
  }
}

output "ecs_cluster_summary" {
  description = "Staging ECS cluster and per-service log destinations."

  value = {
    cluster_arn     = module.ecs_cluster.cluster_arn
    cluster_name    = module.ecs_cluster.cluster_name
    log_group_names = module.ecs_cluster.log_group_names
    log_group_arns  = module.ecs_cluster.log_group_arns
  }
}

output "api_task_definition_arn" {
  description = "Staging API task definition; the API service starts with zero running tasks."
  value       = try(aws_ecs_task_definition.api[0].arn, null)
}

output "database_bootstrap_task_definition_arn" {
  description = "One-off staging database bootstrap task definition; Terraform does not run it."
  value       = try(aws_ecs_task_definition.database_bootstrap[0].arn, null)
}

output "frontend_hosting" {
  description = "Private bucket and AWS-provided HTTPS address for the staging frontend."

  value = {
    bucket_name     = aws_s3_bucket.frontend.id
    distribution_id = aws_cloudfront_distribution.frontend.id
    https_url       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
  }
}