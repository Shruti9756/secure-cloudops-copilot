terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

locals {
  subnet_indexes_by_availability_zone = {
    for index, availability_zone in var.availability_zones :
    availability_zone => index
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  instance_tenancy     = "default"

  tags = {
    Name = "${var.name_prefix}-vpc"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-internet-gateway"
  }
}

resource "aws_subnet" "public" {
  for_each = local.subnet_indexes_by_availability_zone

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, each.value)
  map_public_ip_on_launch = false

  tags = {
    Name        = "${var.name_prefix}-public-${each.value + 1}"
    NetworkTier = "public"
  }
}

resource "aws_subnet" "private" {
  for_each = local.subnet_indexes_by_availability_zone

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, each.value + 10)
  map_public_ip_on_launch = false

  tags = {
    Name        = "${var.name_prefix}-private-${each.value + 1}"
    NetworkTier = "private"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name        = "${var.name_prefix}-public"
    NetworkTier = "public"
  }
}

resource "aws_route" "public_ipv4_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  for_each = local.subnet_indexes_by_availability_zone

  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  for_each = local.subnet_indexes_by_availability_zone

  vpc_id = aws_vpc.this.id

  tags = {
    Name             = "${var.name_prefix}-private-${each.value + 1}"
    NetworkTier      = "private"
    AvailabilityZone = each.key
  }
}

resource "aws_route_table_association" "private" {
  for_each = local.subnet_indexes_by_availability_zone

  subnet_id      = aws_subnet.private[each.key].id
  route_table_id = aws_route_table.private[each.key].id
}