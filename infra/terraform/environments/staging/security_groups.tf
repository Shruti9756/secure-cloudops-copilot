module "security_groups" {
  source = "../../modules/security-groups"

  name_prefix               = "secure-cloudops-${var.environment}"
  vpc_id                    = module.network.vpc_id
  allow_public_https_egress = true
  enable_publisher          = true

  additional_api_ingress_rule_ids = aws_vpc_security_group_ingress_rule.api_from_private_alb[*].id
}