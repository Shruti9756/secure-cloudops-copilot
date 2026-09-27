ephemeral "aws_secretsmanager_random_password" "cache_auth" {
  password_length     = 48
  exclude_punctuation = true
}

resource "aws_secretsmanager_secret_version" "cache_auth" {
  secret_id                = aws_secretsmanager_secret.cache_auth_token.id
  secret_string_wo         = ephemeral.aws_secretsmanager_random_password.cache_auth.random_password
  secret_string_wo_version = 1
}

ephemeral "aws_secretsmanager_secret_version" "cache_auth" {
  secret_id  = aws_secretsmanager_secret_version.cache_auth.secret_id
  version_id = aws_secretsmanager_secret_version.cache_auth.version_id

  depends_on = [aws_secretsmanager_secret_version.cache_auth]
}

resource "aws_elasticache_replication_group" "staging" {
  replication_group_id       = "secure-cloudops-${var.environment}-cache"
  description                = "Private single-node staging cache"
  engine                     = "valkey"
  engine_version             = "7.2"
  node_type                  = "cache.t4g.micro"
  num_cache_clusters         = 1
  cluster_mode               = "disabled"
  automatic_failover_enabled = false
  port                       = 6379

  subnet_group_name  = aws_elasticache_subnet_group.staging.name
  security_group_ids = [module.security_groups.security_group_ids["cache"]]

  transit_encryption_enabled = true
  transit_encryption_mode    = "required"
  at_rest_encryption_enabled = true

  auth_token_wo              = ephemeral.aws_secretsmanager_secret_version.cache_auth.secret_string
  auth_token_wo_version      = aws_secretsmanager_secret_version.cache_auth.secret_string_wo_version
  auth_token_update_strategy = "ROTATE"

  tags = {
    Name = "secure-cloudops-${var.environment}-cache"
  }
}