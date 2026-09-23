module "ecs_roles" {
  source = "../../modules/ecs-roles"

  name_prefix    = "secure-cloudops-${var.environment}"
  aws_region     = var.aws_region
  aws_account_id = var.aws_account_id
}