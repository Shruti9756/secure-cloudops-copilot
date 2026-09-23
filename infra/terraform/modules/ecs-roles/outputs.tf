output "execution_role_arns" {
  description = "Execution role ARN for each ECS service."
  value = {
    for service, role in aws_iam_role.execution :
    service => role.arn
  }
}

output "task_role_arns" {
  description = "Application task role ARN for each ECS service."
  value = {
    for service, role in aws_iam_role.task :
    service => role.arn
  }
}