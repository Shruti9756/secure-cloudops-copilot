# ADR-0001: Use Amazon ECS Fargate before Kubernetes

## Status

Accepted

## Context

SecureCloudOps Copilot needs containerized deployment on AWS. Kubernetes provides powerful orchestration, but it adds significant operational complexity for an early-stage portfolio project.

## Decision

Use Docker locally and Amazon ECS Fargate for the first cloud deployment.

## Consequences

This lets the project focus on containers, IAM, networking, CI/CD, observability, security, and scalable service design without needing to operate a Kubernetes control plane.

Kubernetes/EKS remains a possible future extension after the ECS-based version is stable.