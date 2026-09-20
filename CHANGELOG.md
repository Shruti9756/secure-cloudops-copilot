# Changelog

All notable project changes are documented in this file.

This project follows semantic versioning. The V0.x releases are learning and portfolio milestones; V1.0 is the final polished portfolio release.

## [Unreleased]

## [0.3.0] - 2026-09-21

### Reliable ingestion and Redis

- Added checksum-based idempotent background document processing with persisted attempt counts, bounded exponential retry, failure reasons, and terminal failure state.
- Added authorized document-processing retry and live browser progress.
- Added Redis distributed document locks with ownership-safe release and lock renewal during embedding.
- Added layered per-user and per-organization request limits and per-organization model-token quotas.
- Added normalized-text embedding caching with provider-token accounting.
- Added workspace knowledge revisions that invalidate cached answers after document changes.

### RAG quality and evaluation

- Added a versioned 50-question retrieval benchmark with reviewed expected document and chunk sources.
- Added custom BM25 lexical retrieval, reciprocal-rank-fusion hybrid search, and an evaluation-only identifier-aware reranker.
- Integrated hybrid retrieval into the production RAG path with semantic anchoring for safe abstention.
- Added precision, recall, mean latency, P50 latency, P95 latency, and query-token measurements.
- Added an eight-case grounded-answer and safe-abstention benchmark.
- Added a controlled comparison of `1200/200` and `600/100` chunking profiles.
- Published a consolidated V0.3 evaluation report covering quality, latency, token usage, tradeoffs, and limitations.
- Deferred optional Ragas judge-model evaluation while retaining transparent custom metrics.

### Verification

- Default API suite: 459 passed, with one live end-to-end test deselected.
- Hybrid retrieval improved mean Recall@3 from 0.880 to 0.980 on the controlled 50-question corpus.
- Post-hybrid answer evaluation retained 1.000 outcome accuracy, citation correctness, abstention correctness, and overall pass rate.
- The current `1200/200` chunking profile was retained based on measured recall, chunk count, embedding-token, and latency tradeoffs.

### Known limitations

- V0.3 measurements use a small synthetic corpus and one local-development machine.
- Local Ollama token counts are compute proxies, not billed cloud-model costs.
- The local database-backed worker does not yet use Amazon SQS or a dead-letter queue.
- Ragas and broader model-judged evaluation remain optional future work.

## [0.2.0] - 2026-09-04

### Identity, authorization, and isolation

- Added organizations, application users, memberships, tenant workspaces, and `admin`, `manager`, and `engineer` roles.
- Added Cognito Hosted UI authorization-code sign-in with PKCE in the web application.
- Added server-side Cognito access-token validation for issuer, app client, token use, expiry, signature, and JWKS keys.
- Added organization-scoped authorization for RAG, document status, upload, download, deployment, and runbook endpoints.
- Added privacy-preserving cross-workspace denials and safe audit events that correlate the authenticated actor and request ID.
- Added organization scope to implemented tenant-owned documents, chunks, and audit records, plus organization-scoped retrieval and cache keys.
- Added role-aware document access levels: engineers read organization documents; managers and administrators also read restricted documents and may upload or update documents.

### AI safety and RAG integrity

- Added prompt-injection handling for untrusted questions and retrieved evidence.
- Added narrow PII redaction alongside existing secret redaction before persistence, embedding, retrieval, logs, and optional S3 storage.
- Added strict Pydantic validation for model-produced JSON answer and citation shapes before an answer is returned.
- Added a safe withheld-response path for malformed structured model output, invalid citations, and unsafe output.
- Added deterministic generation settings for reproducible local RAG behavior.

### AWS, storage, and user experience

- Added Terraform-managed Amazon Cognito development resources: user pool, web client, managed-login domain, and branding.
- Added authorized, short-lived, version-pinned S3 links for redacted document text only.
- Added workspace and role display, Cognito session handling, role-aware document controls, and secure-link controls in the web UI.
- Added a worker mode that processes pending documents across all tenant workspaces.

### Verification and release evidence

- Automated API suite: 232 passing tests, with one opt-in live end-to-end test deselected from the default suite.
- Captured V0.2 evidence for structured grounded answers, SkyForge role isolation, cross-workspace denial and audit correlation, API quality checks, web quality checks, and Terraform no-drift verification.
- Added V0.2 release and demo documentation.

### Known limitations

- V0.2 remains a local-development learning baseline; it is not a production deployment.
- Database row-level security, workload IAM roles, secrets management, private networking, WAF, CloudTrail, centralized audit retention, and broader red-team/evaluation coverage remain future work.

## [0.1.0] - 2026-08-27

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
