data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing" {
  count = var.runtime_enabled ? 1 : 0
  name  = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "api_private_alb" {
  count       = var.runtime_enabled ? 1 : 0
  name        = "secure-cloudops-${var.environment}-api-private-alb"
  description = "Private API load balancer traffic boundary."
  vpc_id      = module.network.vpc_id

  tags = {
    Name    = "secure-cloudops-${var.environment}-api-private-alb"
    Purpose = "private-api-entry"
  }
}

resource "aws_vpc_security_group_ingress_rule" "api_alb_from_cloudfront" {
  count             = var.runtime_enabled ? 1 : 0
  description       = "Allow CloudFront origin-facing traffic to the private ALB."
  security_group_id = aws_security_group.api_private_alb[0].id
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront_origin_facing[0].id
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "api_alb_to_api" {
  count                        = var.runtime_enabled ? 1 : 0
  description                  = "Allow the private ALB to reach API containers."
  security_group_id            = aws_security_group.api_private_alb[0].id
  referenced_security_group_id = module.security_groups.security_group_ids["api"]
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_rules_exclusive" "api_private_alb" {
  count             = var.runtime_enabled ? 1 : 0
  security_group_id = aws_security_group.api_private_alb[0].id

  ingress_rule_ids = [
    aws_vpc_security_group_ingress_rule.api_alb_from_cloudfront[0].id,
  ]

  egress_rule_ids = [
    aws_vpc_security_group_egress_rule.api_alb_to_api[0].id,
  ]
}

resource "aws_vpc_security_group_ingress_rule" "api_from_private_alb" {
  count                        = var.runtime_enabled ? 1 : 0
  description                  = "Allow API requests only from the private ALB security group."
  security_group_id            = module.security_groups.security_group_ids["api"]
  referenced_security_group_id = aws_security_group.api_private_alb[0].id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
}

resource "aws_lb" "api" {
  count                      = var.runtime_enabled ? 1 : 0
  name                       = "secure-cloudops-${var.environment}-api"
  internal                   = true
  load_balancer_type         = "application"
  ip_address_type            = "ipv4"
  subnets                    = module.network.private_subnet_ids
  security_groups            = [aws_security_group.api_private_alb[0].id]
  enable_deletion_protection = false
  drop_invalid_header_fields = true
  idle_timeout               = 120

  tags = {
    Name    = "secure-cloudops-${var.environment}-api"
    Purpose = "private-api-entry"
  }

  depends_on = [aws_vpc_security_group_rules_exclusive.api_private_alb]
}

resource "aws_lb_target_group" "api" {
  count                = var.runtime_enabled ? 1 : 0
  name                 = "secure-cloudops-${var.environment}-api-tg"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = module.network.vpc_id
  deregistration_delay = 120

  health_check {
    enabled             = true
    path                = "/ready"
    protocol            = "HTTP"
    port                = "traffic-port"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }

  tags = {
    Name = "secure-cloudops-${var.environment}-api-tg"
  }
}

resource "aws_lb_listener" "api_http" {
  count             = var.runtime_enabled ? 1 : 0
  load_balancer_arn = aws_lb.api[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api[0].arn
  }
}