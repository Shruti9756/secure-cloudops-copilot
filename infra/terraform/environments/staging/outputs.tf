output "network_summary" {
  description = "Non-sensitive IDs for the staging network."

  value = {
    vpc_id             = module.network.vpc_id
    availability_zones = module.network.availability_zones
    public_subnet_ids  = module.network.public_subnet_ids
    private_subnet_ids = module.network.private_subnet_ids
    security_group_ids = module.security_groups.security_group_ids
  }
}

output "container_repository_urls" {
  description = "Private ECR URLs for application images."
  value       = module.container_registry.repository_urls
}