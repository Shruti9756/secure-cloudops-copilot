module "ecs_cluster" {
  source = "../../modules/ecs-cluster"

  name_prefix        = "secure-cloudops-${var.environment}"
  log_retention_days = 7
}