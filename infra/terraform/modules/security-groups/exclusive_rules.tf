resource "aws_vpc_security_group_rules_exclusive" "load_balancer" {
  security_group_id = aws_security_group.load_balancer.id

  ingress_rule_ids = [
    aws_vpc_security_group_ingress_rule.load_balancer_https.id,
  ]

  egress_rule_ids = [
    aws_vpc_security_group_egress_rule.load_balancer_to_frontend.id,
    aws_vpc_security_group_egress_rule.load_balancer_to_api.id,
  ]
}

resource "aws_vpc_security_group_rules_exclusive" "frontend" {
  security_group_id = aws_security_group.frontend.id

  ingress_rule_ids = [
    aws_vpc_security_group_ingress_rule.frontend_from_load_balancer.id,
  ]

  egress_rule_ids = aws_vpc_security_group_egress_rule.frontend_https[*].id
}

resource "aws_vpc_security_group_rules_exclusive" "api" {
  security_group_id = aws_security_group.api.id

  ingress_rule_ids = [
    aws_vpc_security_group_ingress_rule.api_from_load_balancer.id,
  ]

  egress_rule_ids = concat(
    [
      aws_vpc_security_group_egress_rule.api_to_database.id,
      aws_vpc_security_group_egress_rule.api_to_cache.id,
    ],
    aws_vpc_security_group_egress_rule.api_https[*].id,
  )
}

resource "aws_vpc_security_group_rules_exclusive" "worker" {
  security_group_id = aws_security_group.worker.id

  ingress_rule_ids = []

  egress_rule_ids = concat(
    [
      aws_vpc_security_group_egress_rule.worker_to_database.id,
      aws_vpc_security_group_egress_rule.worker_to_cache.id,
    ],
    aws_vpc_security_group_egress_rule.worker_https[*].id,
  )
}

resource "aws_vpc_security_group_rules_exclusive" "database" {
  security_group_id = aws_security_group.database.id

  ingress_rule_ids = [
    aws_vpc_security_group_ingress_rule.database_from_api.id,
    aws_vpc_security_group_ingress_rule.database_from_worker.id,
  ]

  egress_rule_ids = []
}

resource "aws_vpc_security_group_rules_exclusive" "cache" {
  security_group_id = aws_security_group.cache.id

  ingress_rule_ids = [
    aws_vpc_security_group_ingress_rule.cache_from_api.id,
    aws_vpc_security_group_ingress_rule.cache_from_worker.id,
  ]

  egress_rule_ids = []
}