output "network_summary" {
  description = "Non-sensitive IDs for the staging network."

  value = {
    vpc_id             = module.network.vpc_id
    availability_zones = module.network.availability_zones
    public_subnet_ids  = module.network.public_subnet_ids
    private_subnet_ids = module.network.private_subnet_ids
  }
}