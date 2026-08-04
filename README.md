# SecureCloudOps Copilot

A secure, multi-tenant AI copilot for AWS incident investigation.

Engineering teams can upload runbooks, postmortems, architecture documents, and deployment records. The copilot uses Retrieval-Augmented Generation (RAG) to return grounded answers with citations, and later uses secure Model Context Protocol (MCP) tools to inspect approved operational context.

## Core capabilities

- Cited RAG over engineering knowledge
- Multi-tenant access control and auditability
- Redis caching, rate limiting, and job coordination
- Custom MCP tools with least-privilege access
- AWS deployment using Docker, ECS, Bedrock, S3, RDS, and Terraform
- AI security: prompt-injection defense, PII protection, output validation, and guardrails
- Observability, testing, CI/CD, and infrastructure as code

## Project status

Current version: **V0.0 — Project Foundation**

The version-by-version implementation plan is available in [VERSIONED_ROADMAP.md](VERSIONED_ROADMAP.md).

## Architecture

> Architecture diagrams will be added as the system is implemented.

## Technology stack

Next.js, TypeScript, FastAPI, Python, PostgreSQL, pgvector, Redis, Docker, Amazon Bedrock, Amazon S3, Amazon ECS, Terraform, MCP, OpenTelemetry, GitHub Actions.

## Security note

This project uses only synthetic demonstration documents. Never commit credentials, AWS keys, real customer data, or production documents.