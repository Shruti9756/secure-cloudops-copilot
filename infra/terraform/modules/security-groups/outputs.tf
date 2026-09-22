output "security_group_ids" {
  description = "Security group IDs for the application tiers."

  value = {
    load_balancer = aws_security_group.load_balancer.id
    frontend      = aws_security_group.frontend.id
    api           = aws_security_group.api.id
    worker        = aws_security_group.worker.id
    database      = aws_security_group.database.id
    cache         = aws_security_group.cache.id
  }
}