module "security_groups" {
  source = "../../modules/security-groups"

  name_prefix               = "secure-cloudops-${var.environment}"
  vpc_id                    = module.network.vpc_id
  allow_public_https_egress = true
}