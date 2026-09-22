resource "aws_security_group" "load_balancer" {
  name        = "${var.name_prefix}-load-balancer"
  description = "Public load balancer traffic boundary."
  vpc_id      = var.vpc_id

  tags = {
    Name         = "${var.name_prefix}-load-balancer"
    SecurityTier = "edge"
  }
}

resource "aws_security_group" "frontend" {
  name        = "${var.name_prefix}-frontend"
  description = "Frontend container traffic boundary."
  vpc_id      = var.vpc_id

  tags = {
    Name         = "${var.name_prefix}-frontend"
    SecurityTier = "application"
  }
}

resource "aws_security_group" "api" {
  name        = "${var.name_prefix}-api"
  description = "API container traffic boundary."
  vpc_id      = var.vpc_id

  tags = {
    Name         = "${var.name_prefix}-api"
    SecurityTier = "application"
  }
}

resource "aws_security_group" "worker" {
  name        = "${var.name_prefix}-worker"
  description = "Background worker traffic boundary."
  vpc_id      = var.vpc_id

  tags = {
    Name         = "${var.name_prefix}-worker"
    SecurityTier = "application"
  }
}

resource "aws_security_group" "database" {
  name        = "${var.name_prefix}-database"
  description = "PostgreSQL traffic boundary."
  vpc_id      = var.vpc_id

  tags = {
    Name         = "${var.name_prefix}-database"
    SecurityTier = "data"
  }
}

resource "aws_security_group" "cache" {
  name        = "${var.name_prefix}-cache"
  description = "Redis traffic boundary."
  vpc_id      = var.vpc_id

  tags = {
    Name         = "${var.name_prefix}-cache"
    SecurityTier = "data"
  }
}