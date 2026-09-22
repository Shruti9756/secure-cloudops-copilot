resource "aws_vpc_security_group_egress_rule" "load_balancer_to_frontend" {
  description       = "Allow the load balancer to reach the frontend."
  security_group_id = aws_security_group.load_balancer.id

  referenced_security_group_id = aws_security_group.frontend.id
  from_port                    = var.frontend_port
  to_port                      = var.frontend_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "load_balancer_to_api" {
  description       = "Allow the load balancer to reach the API."
  security_group_id = aws_security_group.load_balancer.id

  referenced_security_group_id = aws_security_group.api.id
  from_port                    = var.api_port
  to_port                      = var.api_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "api_to_database" {
  description       = "Allow the API to connect to PostgreSQL."
  security_group_id = aws_security_group.api.id

  referenced_security_group_id = aws_security_group.database.id
  from_port                    = var.database_port
  to_port                      = var.database_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "api_to_cache" {
  description       = "Allow the API to connect to Redis."
  security_group_id = aws_security_group.api.id

  referenced_security_group_id = aws_security_group.cache.id
  from_port                    = var.cache_port
  to_port                      = var.cache_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "worker_to_database" {
  description       = "Allow the worker to connect to PostgreSQL."
  security_group_id = aws_security_group.worker.id

  referenced_security_group_id = aws_security_group.database.id
  from_port                    = var.database_port
  to_port                      = var.database_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "worker_to_cache" {
  description       = "Allow the worker to connect to Redis."
  security_group_id = aws_security_group.worker.id

  referenced_security_group_id = aws_security_group.cache.id
  from_port                    = var.cache_port
  to_port                      = var.cache_port
  ip_protocol                  = "tcp"
}