resource "aws_vpc_security_group_ingress_rule" "load_balancer_https" {
  description       = "Allow public HTTPS to the load balancer."
  security_group_id = aws_security_group.load_balancer.id

  cidr_ipv4   = "0.0.0.0/0"
  from_port   = 443
  to_port     = 443
  ip_protocol = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "frontend_from_load_balancer" {
  description       = "Allow frontend traffic only from the load balancer."
  security_group_id = aws_security_group.frontend.id

  referenced_security_group_id = aws_security_group.load_balancer.id
  from_port                    = var.frontend_port
  to_port                      = var.frontend_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "api_from_load_balancer" {
  description       = "Allow API traffic only from the load balancer."
  security_group_id = aws_security_group.api.id

  referenced_security_group_id = aws_security_group.load_balancer.id
  from_port                    = var.api_port
  to_port                      = var.api_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "database_from_api" {
  description       = "Allow PostgreSQL connections from the API."
  security_group_id = aws_security_group.database.id

  referenced_security_group_id = aws_security_group.api.id
  from_port                    = var.database_port
  to_port                      = var.database_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "database_from_worker" {
  description       = "Allow PostgreSQL connections from the worker."
  security_group_id = aws_security_group.database.id

  referenced_security_group_id = aws_security_group.worker.id
  from_port                    = var.database_port
  to_port                      = var.database_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "cache_from_api" {
  description       = "Allow Redis connections from the API."
  security_group_id = aws_security_group.cache.id

  referenced_security_group_id = aws_security_group.api.id
  from_port                    = var.cache_port
  to_port                      = var.cache_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "cache_from_worker" {
  description       = "Allow Redis connections from the worker."
  security_group_id = aws_security_group.cache.id

  referenced_security_group_id = aws_security_group.worker.id
  from_port                    = var.cache_port
  to_port                      = var.cache_port
  ip_protocol                  = "tcp"
}