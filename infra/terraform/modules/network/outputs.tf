output "vpc_id" {
  description = "ID of the environment VPC."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs ordered by the configured Availability Zones."

  value = [
    for availability_zone in var.availability_zones :
    aws_subnet.public[availability_zone].id
  ]
}

output "private_subnet_ids" {
  description = "Private subnet IDs ordered by the configured Availability Zones."

  value = [
    for availability_zone in var.availability_zones :
    aws_subnet.private[availability_zone].id
  ]
}

output "public_route_table_id" {
  description = "Route table used by both public subnets."
  value       = aws_route_table.public.id
}

output "private_route_table_ids" {
  description = "Private route-table IDs ordered by Availability Zone."

  value = [
    for availability_zone in var.availability_zones :
    aws_route_table.private[availability_zone].id
  ]
}

output "availability_zones" {
  description = "Availability Zones used by the network."
  value       = var.availability_zones
}