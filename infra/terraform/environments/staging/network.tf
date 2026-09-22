module "network" {
  source = "../../modules/network"

  name_prefix        = "secure-cloudops-${var.environment}"
  vpc_cidr           = var.network_vpc_cidr
  availability_zones = var.network_availability_zones
}