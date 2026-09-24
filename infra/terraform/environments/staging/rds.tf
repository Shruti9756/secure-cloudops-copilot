resource "aws_db_subnet_group" "staging" {
  name       = "secure-cloudops-${var.environment}-db-subnets"
  subnet_ids = module.network.private_subnet_ids

  tags = {
    Name = "secure-cloudops-${var.environment}-db-subnets"
  }
}

resource "aws_db_instance" "staging" {
  identifier = "secure-cloudops-${var.environment}-db"

  engine         = "postgres"
  engine_version = "17.11"
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name                     = "securecloudops"
  username                    = "securecloudops_admin"
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.staging.name
  vpc_security_group_ids = [module.security_groups.security_group_ids["database"]]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period      = 1
  deletion_protection          = true
  skip_final_snapshot          = false
  final_snapshot_identifier    = "secure-cloudops-${var.environment}-db-final"
  performance_insights_enabled = false
  monitoring_interval          = 0

  tags = {
    Name = "secure-cloudops-${var.environment}-db"
  }
}