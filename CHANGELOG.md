# Changelog

All notable project changes are documented in this file.

This project follows semantic versioning. The V0.x releases are learning and portfolio milestones; V1.0 is the final polished portfolio release.

## [Unreleased]

### Remaining release requirements

- Run a fresh-clone setup verification using the README.
- Open and merge the V0.1 pull request to `main`.
- Create the `v0.1.0` Git tag and GitHub Release.

## [0.1.0] - Release candidate

### Added

- Next.js and TypeScript investigation interface.
- FastAPI service with OpenAPI documentation, health checks, readiness checks, and Prometheus metrics.
- PostgreSQL and pgvector knowledge store with Alembic database migrations.
- Redis response caching and fixed-window API rate limiting.
- Local Ollama embeddings with `mxbai-embed-large` and grounded generation with `qwen3:4b-instruct`.
- Tenant-scoped semantic retrieval with relevance thresholds and safe insufficient-evidence responses.
- Source citations, citation validation, and deterministic output-safety validation.
- Deterministic secret redaction before document storage, chunking, embedding, retrieval, and optional cloud storage.
- Markdown, TXT, digital PDF, and DOCX document-upload support.
- Background Docker worker for automatic chunking and embedding.
- Opt-in live E2E verification for upload, worker processing, Ollama embeddings, and tenant-scoped pgvector retrieval.
- PostgreSQL audit events correlated through server-generated request IDs.
- Custom read-only MCP server for approved knowledge, deployment, and runbook context.
- Prometheus metrics and a local Grafana dashboard.
- GitHub Actions quality checks for API tests, web lint/build, committed-secret scanning, and Terraform formatting/validation.

### AWS and infrastructure

- Private Amazon S3 storage for extracted and redacted document text only.
- S3 Block Public Access, versioning, default AES-256 encryption, and synthetic-data classification tags.
- Fail-closed application behavior when configured S3 storage is unavailable.
- Terraform configuration that manages the existing S3 bucket, public-access block, versioning, encryption, and tags.
- Terraform drift verification showing that real AWS infrastructure matches version-controlled configuration.
- Terraform local state and local variable values excluded from Git.

### Security

- Synthetic-data-only repository policy.
- Secret-redaction tests and safe storage metadata.
- Request IDs for audit correlation without recording raw questions or generated answers.
- Read-only MCP boundaries that prohibit arbitrary shell, SQL, unrestricted AWS, and production-change operations.
- Least-privilege local AWS-profile usage; Docker Compose does not receive host AWS credentials.

### Release evidence

- Screenshot evidence for grounded answers, cache behavior, safe refusal, document processing, Prometheus, GitHub Actions, Terraform, and S3 redaction is stored in `docs/release/screenshots/`.
- A recording is optional portfolio material and is not required to complete V0.1.

### Known limitations

- Amazon Bedrock adapter exists, but model invocation is pending AWS account authorization.
- Local Ollama is the verified development embedding and chat provider.
- Authentication and RBAC are planned for a later release.
- Cloud container deployment to ECR/ECS, managed databases, and remote Terraform state are not part of V0.1.
- The project is designed for synthetic demonstration data only.