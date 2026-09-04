# SecureCloudOps Copilot — Versioned Build Plan

> This is the version-by-version master plan for the project. It complements `PROJECT_ROADMAP.md`, which contains the detailed task checklist.
>
> **Rule:** A later version never replaces an unfinished earlier version. Every version has a working, tested, committed GitHub milestone before the next one begins.

## The project in one sentence

**SecureCloudOps Copilot** is a secure, multi-tenant AI platform that helps engineering teams investigate AWS incidents using approved documents, cited RAG answers, and controlled MCP tools.

## Non-negotiable product rules

- The model must not invent citations or claim evidence it did not retrieve.
- Tenant and role authorization are enforced by the application and datastore, never merely written in a prompt.
- Documents and tool outputs are untrusted input and may contain prompt injection.
- MCP tools begin read-only. No arbitrary shell, arbitrary URL, or unrestricted AWS access is ever given to a model.
- Secrets never enter source control, prompts, document corpora, or ordinary logs.
- Every version is documented in GitHub with a release note, test evidence, and a demo/screenshot when relevant.

## Version map

| Version | Main outcome | Target timing | Portfolio value |
|---|---|---|---|
| V0.0 | Project foundation | Days 1–3 | Demonstrates planning and engineering ownership |
| V0.1 | Local RAG MVP | By 2 September 2026 | A complete, demoable AI application |
| V0.2 | Multi-tenant secure RAG | After V0.1 | Demonstrates backend design and AI safety |
| V0.3 | Reliable, measurable RAG | After V0.2 | Demonstrates performance, async design, and evaluation |
| V0.4 | AWS cloud platform | After V0.3 | Demonstrates containers, IaC, cloud architecture |
| V0.5 | Custom MCP investigation agent | After V0.4 | Demonstrates modern agent/tool engineering |
| V0.6 | Production security and operations | After V0.5 | Demonstrates SDE-2 production readiness |
| V1.0 | Portfolio release | After V0.6 | Demonstrates end-to-end ownership |
| V1.1 | Advanced/enterprise extensions | Optional | Demonstrates architectural depth |

---

# V0.0 — Project foundation

**Purpose:** Make the project organized before application code is written.

## Build

- [ ] Create the GitHub repository and add a clear description.
- [ ] Keep `PROJECT_ROADMAP.md` and this file at the repository root.
- [ ] Create the GitHub Project board: `Backlog`, `Ready`, `In progress`, `In review`, `Done`.
- [ ] Create issues from the V0.1 checklist first; create later-version issues as epics.
- [ ] Create folders: `apps/`, `services/`, `infra/`, `docs/`, `tests/`.
- [ ] Create synthetic e-commerce documents: runbooks, postmortems, architecture notes, deployment records, and metric snapshots.
- [ ] Write two ADRs: why ECS precedes Kubernetes; why authorization happens before RAG retrieval.
- [ ] Draw an initial architecture diagram and upload it to `docs/architecture/`.
- [ ] Add a `.gitignore`, `.env.example`, license, contribution guidance, and code-of-conduct decision.

## Technologies introduced

- Git and GitHub
- Markdown documentation
- Architecture Decision Records (ADRs)
- GitHub Issues and GitHub Projects

## Release gate

- [ ] A reviewer can understand the product, architecture, scope, and next five tasks without asking you questions.

---

# V0.1 — Local RAG MVP

**Purpose:** Deliver a small but complete locally runnable AI product by **2 September 2026**. This is the deadline release.

## Early cloud-storage checkpoint — completed 25 August 2026

- [x] Created a private Amazon S3 bucket with Block Public Access, versioning, default encryption, and synthetic-data tags.
- [x] Added a fail-closed S3 storage adapter for extracted and redacted document text.
- [x] Stored only safe S3 references in PostgreSQL: provider, bucket, key, version ID, and ETag.
- [x] Verified a real host API upload reaches S3 with explicit AES-256 encryption and redacted content.
- [x] Verified the Docker worker subsequently chunks and embeds the uploaded document.
- [x] Kept Docker Compose free of host AWS credentials; future ECS tasks will use IAM roles.

## User experience

1. A user opens the web app.
2. They upload a synthetic runbook or architecture document.
3. The system processes it.
4. They ask a question.
5. They receive a grounded answer with source citations.
6. They can see the document/chunk that supports the response.

## Build

### Monorepo and local environment

- [ ] Create `apps/web` for the frontend.
- [ ] Create `services/api` for the API and RAG orchestration.
- [ ] Create `services/worker` for document-processing code.
- [ ] Create `services/mcp-server` as a placeholder; implement it fully in V0.5.
- [ ] Create `docker-compose.yml` for web, API, worker, PostgreSQL, and Redis.
- [ ] Document the local setup in the README.

### Web application

- [ ] Create a Next.js + TypeScript app.
- [ ] Use Tailwind CSS for a clean responsive UI.
- [ ] Use TanStack Query for API/server state.
- [ ] Build upload, document-status, chat, citation/source, loading, and error views.
- [ ] Keep authentication simple in V0.1; production identity comes later.

### API and database

- [ ] Create FastAPI routes with `/health` and versioned `/api/v1` endpoints.
- [ ] Use Pydantic schemas for request/response validation.
- [ ] Use SQLAlchemy for database access and Alembic for PostgreSQL migrations.
- [ ] Create basic models: `Document`, `DocumentVersion`, `IngestionJob`, `Conversation`, `Message`, `Citation`, and `AuditEvent`.
- [ ] Use PostgreSQL with the `pgvector` extension as the first vector store.
- [ ] Add basic structured JSON logs.

### Custom RAG

- [ ] Accept Markdown, TXT, PDF, and DOCX files.
- [ ] Use PyMuPDF for PDFs and `python-docx` for DOCX extraction.
- [x] Optionally mirror redacted extracted text to a private, encrypted, versioned Amazon S3 bucket for cloud demo evidence.
- [ ] Normalize extracted text while retaining heading/page information.
- [ ] Implement chunking with documented chunk size and overlap.
- [ ] Generate embeddings with Amazon Bedrock when AWS is available; use an optional local development provider when not.
- [ ] Store chunks, vectors, and page/section metadata in pgvector.
- [ ] Retrieve top-k chunks using semantic similarity.
- [ ] Create the generation prompt yourself; do not hide the initial RAG logic inside a framework.
- [ ] Return document name, version, and page/section in every citation.
- [ ] Return “I do not have enough evidence” when retrieval does not support an answer.

### Redis — V0.1 starter scope

- [ ] Run Redis in Docker Compose.
- [ ] Cache one safe, document-version-aware RAG response path using TTL.
- [ ] Add one fixed-window or sliding-window API rate-limit rule.
- [ ] Handle a Redis outage gracefully; it must not bypass authorization or crash the entire app.

### Minimal AWS exposure

- [x] Install and configure AWS CLI with an IAM identity, never root credentials.
- [ ] Enable model access in Amazon Bedrock for a low-cost test model/embedding model suitable for the selected region.
- [x] Use `boto3` for Bedrock and S3 integrations.
- [x] Create one encrypted S3 demo bucket for synthetic documents only.
- [ ] Set AWS Budget alerts before invoking paid services.

### Testing and GitHub

- [ ] Add Pytest unit tests for chunking, citation mapping, and cache keys.
- [ ] Add a small integration test: upload → ingestion → retrieval → cited answer.
- [ ] Add a GitHub Actions workflow for linting, tests, and secret scanning.
- [ ] Add Gitleaks for committed-secret scanning.
- [ ] Write a release note for `v0.1.0` and record a short local demo video.

## Technologies introduced

- Next.js, TypeScript, Tailwind CSS, TanStack Query
- Python, FastAPI, Pydantic, SQLAlchemy, Alembic
- Docker, Docker Compose
- PostgreSQL, pgvector, Redis
- PyMuPDF, `python-docx`
- Amazon Bedrock, Amazon S3, AWS CLI, `boto3`
- RAG fundamentals: chunking, embeddings, vector search, prompt augmentation, citations
- Pytest, GitHub Actions, Gitleaks

## Explicitly not required yet

- Amazon Cognito, ECS, ECR, RDS, ElastiCache, OpenSearch, SQS, ALB, WAF, and Terraform deployment.
- MCP implementation, autonomous agents, tool access to real AWS telemetry.
- Hybrid retrieval, reranking, Ragas, deep red-team testing, and load testing.

## Release gate

- [ ] A fresh clone can run the local system using the README.
- [ ] A user can upload a document and get a correct, cited answer.
- [ ] The demo includes Docker, Redis, pgvector, Bedrock, and S3 evidence.
- [ ] The GitHub `v0.1.0` release includes screenshots/demo link and test status.

---

# V0.2 — Multi-tenant secure RAG

**Purpose:** Convert the single-user MVP into a real backend platform with enforceable isolation.

## Build

- [x] Add `Organization`, `User`, `Membership`, and `Role` entities.
- [x] Add roles: `admin`, `manager`, `engineer`.
- [x] Add `organization_id` to implemented tenant-owned document, chunk, retrieval, cache, and audit records.
- [x] Require authorized organization context in protected API requests.
- [x] Enforce organization and role filtering before vector retrieval.
- [x] Add document access-level metadata and queries.
- [x] Add Amazon Cognito authentication and JWT validation.
- [x] Add organization-aware frontend navigation and document views.
- [x] Add version-pinned presigned S3 download URLs where appropriate; uploads remain API-mediated so redaction happens before storage.
- [x] Expand audit events to record authenticated sessions, document operations, RAG outcomes, denied access, and quota decisions.
- [x] Add tests proving Organization A cannot infer, retrieve, cite, or access data from Organization B.

## AI safety foundation

- [x] Separate system instruction, user input, and retrieved text by clear delimiters/trust labels.
- [x] Treat uploaded documents as untrusted input.
- [x] Add basic prompt-injection detection/flagging for user input and document chunks.
- [x] Add PII/secret redaction before logs and model calls where appropriate.
- [x] Use strict structured output validation for citations and answer shape.

## Technologies introduced

- Amazon Cognito, JWT, RBAC
- Presigned Amazon S3 URLs
- Multi-tenancy and row/query-level authorization patterns
- PII/secrets redaction
- Bedrock Guardrails introduction

## Release gate

- [x] Separate organizations can use the system without cross-tenant data exposure in the verified local baseline.
- [x] Unauthorized questions and retrievals are denied and audited.

## Completion evidence

- [x] V0.2 release evidence is captured in `docs/release/screenshots/v0.2/`.
- [x] Merged V0.2 release pull request #2 to `main` after eight required GitHub Actions checks passed.
- [x] Created annotated Git tag `v0.2.0` and published the matching GitHub Release.
- [ ] Prompt-injection and PII tests exist and pass.

---

# V0.3 — Reliable, measurable RAG

**Purpose:** Improve quality, performance, and resilience using evidence.

## Early local processing checkpoint — completed 22 August 2026

> This is an early local implementation to make the V0.1 upload experience automatic. It does not complete V0.3: there is no durable job queue, Redis lock, exponential backoff, persisted failure reason, authenticated job authorization, or AWS SQS/DLQ integration yet.

- [x] Added a separate local Docker Compose worker container with no exposed HTTP port.
- [x] Reused the API image and locked dependencies while running a separate `python -m app.worker` process.
- [x] Added tenant-scoped polling for pending documents with a configurable five-second local interval.
- [x] Reused the tested chunking and local Ollama embedding services rather than duplicating RAG logic.
- [x] Added an explicit SQLAlchemy transaction flush so one worker cycle can safely perform `pending → chunked → embedded` before commit.
- [x] Kept each processing cycle transactional: an embedding failure rolls back derived chunk/vector writes and allows a later retry.
- [x] Logged safe operational counts only—never document content, embeddings, or secrets.
- [x] Added unit tests for tenant scoping, invalid worker configuration, and transaction boundaries: API suite at 131 passing tests.
- [x] Verified live that an uploaded document was automatically chunked and embedded by the worker without manual processing commands.

## Reliable ingestion and Redis

- [ ] Move document processing to a dedicated background-worker flow.
- [ ] Use idempotency keys/checksums to prevent duplicate embeddings.
- [ ] Add retry with bounded exponential backoff.
- [ ] Add failure status, reason, and authorized retry from the UI.
- [ ] Use Redis distributed locks to prevent duplicate processing.
- [ ] Store short-lived job status/progress in Redis.
- [ ] Add per-user and per-organization rate limits.
- [ ] Add per-organization model-token/cost quotas.
- [ ] Cache embedding results by normalized-text hash.
- [ ] Define cache invalidation on document/version/permission changes.

## RAG quality

- [ ] Build a 50–100-question synthetic evaluation dataset.
- [ ] Track expected document/chunk sources for each test question.
- [ ] Measure retrieval precision@k and recall@k.
- [ ] Measure citation correctness and abstention correctness.
- [ ] Add BM25 keyword retrieval with `rank-bm25`.
- [ ] Combine semantic and keyword retrieval into hybrid search.
- [ ] Add a reranker only after creating a baseline.
- [ ] Compare chunking configurations using the evaluation set.
- [ ] Use Ragas as an optional second evaluation framework; retain transparent custom metrics too.
- [ ] Publish an evaluation report showing a measured improvement.

## Technology introduced

- Background worker architecture, retry, idempotency, dead-letter reasoning
- Advanced Redis patterns: locks, quotas, job state, cache invalidation
- Hybrid search, BM25, reranking
- RAG evaluation: precision, recall, groundedness, faithfulness, citation quality, Ragas

## Release gate

- [ ] Ingestion is asynchronous, retryable, and idempotent.
- [ ] At least one retrieval improvement is backed by a reproducible measurement.
- [ ] The README/evaluation report explains quality, latency, and cost tradeoffs.

# V0.4 — AWS cloud platform

**Purpose:** Deploy the proven system as containers on AWS using infrastructure as code. Start with a cost-conscious staging setup; do not keep all services running continuously while learning.

## Infrastructure as code

- [ ] Create Terraform modules and separate `dev`/`staging` environments.
- [ ] Run `terraform fmt`, validation, and plan in CI.
- [ ] Tag all AWS resources with project, environment, owner, and cost-center.
- [ ] Configure budget alerts and clean-up instructions before applying infrastructure.
- [ ] Use `terraform destroy` only for a reviewed, explicitly selected non-production environment.

## AWS core services

- [ ] Create VPC, public/private subnets, route tables, and minimal security groups.
- [ ] Understand the cost/security tradeoff of NAT gateways; avoid them until required.
- [ ] Create ECR repositories for Docker images.
- [ ] Build and push immutable SHA-tagged images.
- [ ] Deploy frontend/API/worker containers to Amazon ECS Fargate.
- [ ] Use an Application Load Balancer and HTTPS for public application traffic.
- [ ] Move PostgreSQL to Amazon RDS with backups, encryption, and private access.
- [ ] Move Redis to Amazon ElastiCache when the workload needs distributed cloud caching.
- [ ] Use S3 as the source-document store with encryption, versioning, lifecycle rules, and least-privilege policies.
- [ ] Replace local ingestion triggering with Amazon SQS and a dead-letter queue.
- [ ] Use Amazon Secrets Manager for database credentials and sensitive configuration.
- [ ] Use IAM task roles with least privilege for each ECS service.
- [ ] Use KMS for encryption where required.
- [ ] Use CloudWatch log groups, metrics, alarms, and dashboard.
- [ ] Use AWS X-Ray as needed alongside OpenTelemetry traces.

## Vector-store progression

- [ ] First cloud deployment: use RDS PostgreSQL + pgvector to control complexity/cost.
- [ ] Evaluate Amazon OpenSearch Serverless only when the evaluation dataset/workload justifies it.
- [ ] If OpenSearch Serverless is selected, configure a conservative OCU cap and understand its billing.
- [ ] Document why the project uses pgvector or OpenSearch in the chosen environment.

## Deployment pipeline

- [ ] Authenticate GitHub Actions to AWS using OIDC; never store long-lived AWS keys in GitHub.
- [ ] Build, scan, push, and deploy images from GitHub Actions.
- [ ] Run controlled database migrations.
- [ ] Add a staging smoke test and rollback instructions.

## Technologies introduced

- Terraform
- AWS VPC, IAM, KMS, Secrets Manager
- ECR, ECS Fargate, Application Load Balancer
- RDS PostgreSQL, ElastiCache, S3, SQS/DLQ
- CloudWatch, X-Ray
- GitHub Actions OIDC
- Amazon OpenSearch Serverless evaluation

## Release gate

- [ ] `terraform plan` makes the AWS environment reproducible.
- [ ] Staging supports sign-in, upload, ingestion, retrieval, citations, and auditing.
- [ ] Stateful services are not public and no secret is committed to GitHub.
- [ ] A cost clean-up procedure is documented and tested for the staging environment.

---

# V0.5 — Custom MCP investigation agent

**Purpose:** Build a custom MCP **server** that uses the standard MCP protocol and exposes safe, project-specific capabilities. We do not invent our own MCP protocol.

## Early local MCP checkpoint — completed 17 August 2026

> This is an early local implementation for hands-on MCP learning. It does not complete the V0.5 release gate: authentication, audit records, Docker packaging, ECS deployment, and real AWS/CloudWatch integrations remain future work.

- [x] Built a separate Python MCP server using the official MCP SDK and local STDIO transport.
- [x] Implemented and tested read-only tools:
  - `get_investigation_scope`
  - `search_incident_knowledge`
  - `get_deployment_context`
- [x] Added a fixed-endpoint API adapter; the MCP server cannot call arbitrary URLs, shell commands, SQL, or AWS APIs.
- [x] Added typed input validation, bounded request parameters, safe upstream-error mapping, and 60-second API deadlines.
- [x] Added and tested the `securecloudops://runbooks/{runbook_name}` resource template.
- [x] Added and tested the user-selected `investigate-deployment-impact` MCP prompt.
- [x] Verified the search tool, deployment tool, runbook resource, and prompt live with MCP Inspector.
- [x] Added unit-test coverage for adapter boundaries, invalid input, not-found cases, rate-limit responses, resources, and prompts: 23 tests passing.

## MCP server

- [ ] Implement a separate Python MCP server using the official MCP SDK / FastMCP.
- [ ] Package the MCP server as a Docker container.
- [ ] Define strict Pydantic/JSON schemas for every tool input and output.
- [ ] Propagate authenticated user, organization, role, conversation ID, and trace ID to every tool request.
- [ ] Add timeouts, request IDs, safe retries, structured failures, and audit events.
- [ ] Add a tool allowlist and deny unknown/unregistered tool requests.

## Version 1 tools — read-only by default

- [ ] `search_runbooks(query, service)` — searches only authorized organization content.
- [ ] `get_metric_summary(service, metric, start_time, end_time)` — returns bounded metric summary data.
- [ ] `get_deployment_context(service, start_time, end_time)` — returns known deployment metadata.
- [ ] `get_incident_history(service)` — returns sanitized incident history.
- [ ] `create_incident_summary_draft(conversation_id)` — creates an internal draft only; no external ticket or production change.

## Agent safety

- [ ] Validate all model-generated arguments on the server.
- [ ] Recheck authorization inside every tool, not only at the API gateway.
- [ ] Redact secrets/PII from tool results.
- [ ] Use dedicated, read-only least-privilege IAM roles for any real AWS/CloudWatch integration.
- [ ] Require explicit user approval before any future write-capable tool action.
- [ ] Add test cases for tool abuse, unknown tools, cross-tenant calls, oversized inputs, and tool timeout.
- [ ] Show tool calls and tool-result citations in the UI.

## AWS MCP options

- [ ] First deployment: run the custom MCP server in ECS Fargate.
- [ ] Advanced comparison: deploy an MCP-compatible server using Amazon Bedrock AgentCore Runtime.
- [ ] Document the tradeoff between direct ECS deployment and AgentCore deployment.

## Technologies introduced

- Model Context Protocol (MCP), FastMCP / official MCP SDK
- Tool schemas, tool authorization, allowlisting, and confirmation workflows
- Amazon CloudWatch read-only integrations
- Amazon Bedrock AgentCore (advanced deployment option)

## Release gate

- [ ] The assistant combines cited RAG context with at least two controlled tool results.
- [ ] All tools are read-only or draft-only, scoped to the caller, and fully audited.
- [ ] No model path can reach arbitrary shell commands, generic AWS CLI access, or unrestricted APIs.

---

# V0.6 — Production AI security and operations

**Purpose:** Make the system observable, resilient, and defensible.

## Early local AI-security checkpoint — updated 20 August 2026

> This is early local implementation for hands-on security learning. It does not complete V0.6: authentication/RBAC, comprehensive audit coverage, Bedrock Guardrails, cloud controls, CI scanning, observability, and deployment security remain future work.

- [x] Added deterministic output-safety validation for selected unsafe operational recommendations.
- [x] Added a versioned AI-security evaluation catalogue and automated catalogue validation.
- [x] Added narrow, deterministic secret redaction before document storage, chunking, embedding, and retrieval.
- [x] Added tests proving redacted content and non-sensitive redaction metadata reach the ingestion database model.
- [x] Added PostgreSQL audit events for completed, cached, denied, and failed RAG request paths, plus accepted and denied Markdown/TXT document uploads, without recording raw questions, answers, uploaded document bodies, or redacted secrets.
- [x] Added a safe API document-upload path: strict Markdown/TXT validation, UTF-8 and size checks, stable source paths, secret redaction before PostgreSQL storage, and request-ID-linked audit events.
- [x] Published this local STRIDE and OWASP LLM-oriented threat model.
- [x] Added server-generated request IDs to API responses and linked each handled RAG request outcome to its audit event.


## AI and cloud security

- [ ] Write a threat model using STRIDE and OWASP LLM Top 10.
- [ ] Document assets, data flows, actors, trust boundaries, and ranked risks.
- [ ] Configure Bedrock Guardrails for appropriate content, topic, and sensitive-information policies.
- [ ] Test prompt injection in user questions, retrieved documents, and MCP tool responses.
- [ ] Add contextual-grounding/citation checks where applicable.
- [ ] Validate output schemas and safely reject invalid model responses.
- [ ] Apply content-security policy, secure headers, CORS restrictions, and secure cookie settings.
- [ ] Add AWS WAF in front of public cloud endpoints when deploying publicly.
- [ ] Enable CloudTrail and protect/review audit records.
- [ ] Run Trivy dependency/container/IaC scans and Gitleaks scans in CI.
- [ ] Generate an SBOM as a supply-chain-security extension.

## Observability and reliability

- [ ] Add OpenTelemetry tracing from browser/API through database, Redis, queue, RAG retrieval, Bedrock, and MCP tools.
- [ ] Use correlation IDs throughout.
- [ ] Create CloudWatch dashboards for API latency/errors, queue age, worker failure, RAG latency, cache hit rate, Bedrock token/cost usage, and tool failures.
- [ ] Add alarms for failures, quota spikes, dead-letter messages, and suspicious denied activity.
- [ ] Add liveness/readiness probes, timeouts, retry policy, and graceful dependency fallbacks.
- [ ] Run k6 load tests for upload and chat journeys.
- [ ] Document an outage exercise: Redis, vector-store, model provider, or queue unavailable.

## Safe rollout

- [ ] Add AWS AppConfig feature flags for model selection, MCP-tool enablement, safety policy configuration, and throttling controls.
- [ ] Configure a gradual rollout/rollback approach for risky AI features.
- [ ] Run red-team test scenarios in CI or a controlled pre-release suite.

## Technologies introduced

- OWASP LLM Top 10, STRIDE, threat modeling, red teaming
- Bedrock Guardrails, AWS WAF, CloudTrail
- OpenTelemetry, CloudWatch dashboards/alarms, X-Ray
- k6 load testing
- Trivy, SBOM, supply-chain security
- AWS AppConfig feature flags and rollout controls

## Release gate

- [ ] Threat model and red-team results are published under `docs/security/`.
- [ ] One trace explains a full RAG/MCP request end-to-end.
- [ ] The team can detect, diagnose, and safely degrade during a simulated dependency failure.

---

# V1.0 — Portfolio release

**Purpose:** Present the finished work as an SDE-2-quality project rather than a code dump.

## GitHub quality

- [ ] Protect the `main` branch and require passing checks.
- [ ] Use short-lived branches and pull requests with tests/security notes.
- [ ] Use conventional, descriptive commits.
- [ ] Link PRs to issues and document significant decisions through ADRs.
- [ ] Publish versioned release notes for V0.1 through V1.0.
- [ ] Ensure no synthetic document accidentally resembles or contains real employer/customer data.

## Documentation and demonstration

- [ ] Rewrite the README for a new reviewer: problem, solution, architecture, stack, local setup, cloud setup, security, evaluation, and demo.
- [ ] Add architecture, data-flow, threat-model, and deployment diagrams.
- [ ] Publish a RAG evaluation report and an AI-security test report.
- [ ] Record a 3–5 minute demo: authentication, upload, ingestion, grounded answer, citations, MCP tools, audit trail, and observability.
- [ ] Prepare a one-page system-design discussion guide.
- [ ] Add screenshots/GIFs without exposing credentials or sensitive data.

## Resume preparation

- [ ] Record real metrics: test coverage, retrieval improvement, cache hit rate, latency, processing time, or model cost reduction.
- [ ] Write two or three resume bullets with measured outcomes.
- [ ] Prepare interview answers on the hardest tradeoff, a production failure, tenant isolation, RAG evaluation, MCP safety, and AWS cost control.

## Release gate

- [ ] A reviewer can run locally, understand the architecture, verify key tests, and watch the principal user flow.
- [ ] The project has one concise, evidence-based resume story.

---

# V1.1 — Advanced and enterprise extensions

**Purpose:** Continue learning after the portfolio release without destabilizing V1.0.

- [ ] Add document-level permission models and richer authorization policy.
- [ ] Add multimodal retrieval for diagrams/screenshots.
- [ ] Add an AWS CloudWatch integration using an isolated read-only role.
- [ ] Add an external ticketing integration only through a human approval workflow.
- [ ] Add policy-as-code for MCP tool authorization if the project needs more complex policies.
- [ ] Add canary/blue-green deployment strategy.
- [ ] Add a disaster-recovery and multi-region architecture design.
- [ ] Compare self-managed RAG against Amazon Bedrock Knowledge Bases.
- [ ] Compare ECS-hosted MCP with AgentCore-hosted MCP.
- [ ] Add a privacy/retention policy and data-deletion workflow.
- [ ] Evaluate multi-model routing by cost, latency, and quality.

---

# Master technology register — nothing is lost

This is the authoritative inventory of every planned technology and where it will be covered. Check it only after hands-on implementation and documentation.

| Technology / concept | Version | Status |
|---|---|---|
| Git, GitHub, issues, PRs, Projects, releases | V0.0–V1.0 | [ ] |
| ADRs, architecture diagrams, system design | V0.0–V1.0 | [ ] |
| Next.js, React, TypeScript, Tailwind | V0.1 | [ ] |
| TanStack Query | V0.1 | [ ] |
| Python, FastAPI, Pydantic | V0.1 | [ ] |
| SQLAlchemy, Alembic | V0.1 | [ ] |
| PostgreSQL | V0.1, V0.4 | [ ] |
| pgvector | V0.1–V0.4 | [ ] |
| Docker, Docker Compose | V0.1 | [ ] |
| Redis: cache, rate limit, locks, job state, quotas | V0.1–V0.3 | [ ] |
| PDF/DOCX parsing: PyMuPDF, `python-docx` | V0.1 | [ ] |
| Custom RAG: chunking, embeddings, retrieval, prompts, citations | V0.1 | [ ] |
| Amazon Bedrock and `boto3` | V0.1 onward | [ ] |
| Amazon S3 and presigned URLs | V0.1, V0.2, V0.4 | [x] V0.1/V0.2 local baseline |
| RAG tenant filters and RBAC | V0.2 | [x] |
| Amazon Cognito, JWT | V0.2 | [x] |
| AI safety: injection defense, output validation, PII redaction | V0.2, V0.6 | [x] V0.2 baseline; V0.6 hardening remains |
| Bedrock Guardrails | V0.2, V0.6 | [ ] |
| Async processing, retries, idempotency | V0.3 | [ ] |
| Hybrid search, BM25, `rank-bm25`, reranking | V0.3 | [ ] |
| RAG evaluation, custom metrics, Ragas | V0.3 | [ ] |
| Terraform | V0.4 | [ ] |
| VPC, security groups, IAM, KMS, Secrets Manager | V0.4 | [ ] |
| ECR, ECS Fargate, ALB | V0.4 | [ ] |
| Amazon RDS | V0.4 | [ ] |
| Amazon ElastiCache | V0.4 | [ ] |
| Amazon SQS and dead-letter queues | V0.4 | [ ] |
| Amazon OpenSearch Serverless | V0.4, optional | [ ] |
| GitHub Actions, AWS OIDC, CI/CD | V0.1, V0.4 | [ ] |
| MCP protocol, official Python MCP SDK / FastMCP | V0.5 | [x] |
| MCP schemas, auth, allowlists, approvals, audit | V0.5 | [ ] |
| Bedrock AgentCore comparison | V0.5 / V1.1 | [ ] |
| OWASP LLM Top 10, STRIDE, threat model, red team | V0.6 | [ ] |
| AWS WAF, CloudTrail | V0.6 | [ ] |
| OpenTelemetry, CloudWatch, X-Ray | V0.4, V0.6 | [ ] |
| Pytest, integration tests, Playwright | V0.1 onward | [ ] |
| k6 load testing | V0.6 | [ ] |
| Gitleaks, Trivy, SBOM | V0.1, V0.6 | [ ] |
| AWS AppConfig feature flags | V0.6 | [ ] |
| Cost controls, budgets, resource tagging/cleanup | V0.1, V0.4 | [ ] |

## How we will track progress together

At the start of every session, state the current version and one small goal, for example:

> “Current version: V0.1. Today: run PostgreSQL and Redis through Docker Compose, then prove both health checks work.”

At the end of every session:

1. Check only completed tasks in this document.
2. Commit the working change with a descriptive message.
3. Add a short note to the relevant GitHub issue: what changed, how it was tested, and what is next.
4. Do not start a new version until its release gate is satisfied.

## Resume outcome at V1.0

> Built SecureCloudOps Copilot, a multi-tenant AWS incident-investigation platform using FastAPI, Next.js, Docker, ECS Fargate, Bedrock, OpenSearch, Redis, and Terraform; implemented cited RAG, secure MCP-based tooling, tenant-isolated retrieval, AI security controls, CI/CD, and end-to-end observability.

Replace generic language with real metrics after implementation.
