output "cluster_arn" {
  description = "ARN of the staging ECS cluster."
  value       = aws_ecs_cluster.this.arn
}

output "cluster_name" {
  description = "Name of the staging ECS cluster."
  value       = aws_ecs_cluster.this.name
}

output "log_group_names" {
  description = "Log group name for each service."
  value = {
    for service, log_group in aws_cloudwatch_log_group.service :
    service => log_group.name
  }
}

output "log_group_arns" {
  description = "Log group ARN for each service."
  value = {
    for service, log_group in aws_cloudwatch_log_group.service :
    service => log_group.arn
  }
}