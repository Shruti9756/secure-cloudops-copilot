# ADR-0002: Mirror only redacted extracted text to private Amazon S3

**Status:** Accepted  
**Date:** 25 August 2026

## Context

SecureCloudOps Copilot accepts synthetic Markdown, text, PDF, and DOCX incident documents. Before documents are stored, chunked, embedded, or retrieved, the application extracts their text and applies deterministic secret redaction.

The project needs a real AWS storage integration that demonstrates cloud-security practices without storing raw uploaded files or secrets in cloud storage.

## Decision

SecureCloudOps Copilot stores only extracted and redacted UTF-8 text in Amazon S3 when the `s3` document-storage backend is enabled.

The implementation follows these rules:

- Original uploaded files are not mirrored to S3 in this V0.1 implementation.
- PDF and DOCX files are first converted to extracted text.
- Secret redaction happens before the S3 upload.
- Each object is tenant-scoped under:

  `tenants/<tenant>/redacted-documents/<source-path>.txt`

- S3 writes explicitly request AES-256 server-side encryption.
- The S3 bucket has Block Public Access, versioning, default encryption, and synthetic-data classification tags enabled.
- PostgreSQL stores only safe storage-reference metadata: provider, bucket name, object key, version ID, and ETag.
- The application fails closed: if S3 storage is configured but unavailable, the document is not accepted into the knowledge base.
- The API returns a safe `503` response and records a safe audit event; it does not expose cloud-provider error details.
- Local Docker Compose intentionally does not mount host AWS credentials. Host-mode verification uses an AWS CLI profile only for local development. A future ECS deployment will use a task IAM role instead.

## Consequences

### Benefits

- Demonstrates a real AWS integration with private, versioned, encrypted object storage.
- Reduces the risk of storing raw secrets or source-file binaries in S3.
- Preserves a versioned evidence copy of the redacted text used by the RAG pipeline.
- Keeps the database lightweight while retaining a traceable S3 reference.
- Makes storage failures visible instead of silently creating incomplete knowledge records.

### Trade-offs

- The original PDF or DOCX file cannot be reconstructed from the S3 object.
- This version does not provide signed download URLs or document restoration workflows.
- The S3 backend requires valid AWS credentials only when enabled.
- Docker Compose remains intentionally S3-disabled to avoid mounting developer AWS credentials into containers.

## Future work

- Replace host AWS profiles with least-privilege ECS task roles.
- Add KMS customer-managed key support if stronger key-control requirements arise.
- Add S3 lifecycle rules and retention policies.
- Add a separate quarantined raw-file storage design only if the product later requires original-file retention.
- Add CloudTrail, Security Hub, and AWS Config evidence for cloud auditing.