module "container_registry" {
  source = "../../modules/container-registry"

  name_prefix           = "secure-cloudops-${var.environment}"
  image_retention_count = 10
}