# SecureCloudOps Copilot

SecureCloudOps Copilot is a security-focused, multi-tenant AI assistant for investigating cloud and production incidents from approved engineering knowledge.

Teams can upload synthetic runbooks, deployment records, Markdown, TXT, digital PDF, and DOCX documents. The system redacts sensitive content, processes documents into embeddings, retrieves only evidence the caller is authorized to access, and returns grounded answers with source citations.

> This repository uses only synthetic demonstration data. Never upload real production documents, credentials, customer data, or AWS keys.

## Current status

[V0.1.0](https://github.com/Shruti9756/secure-cloudops-copilot/releases/tag/v0.1.0) is released.

The project is currently completing V0.2: **multi-tenant secure RAG**. V0.2 adds Cognito authentication, organization and workspace isolation, role-based access control, document visibility levels, safer audit events, PII redaction, and authorized S3 document downloads.

## What works today

- Next.js and TypeScript investigation UI
- FastAPI API with OpenAPI documentation
- PostgreSQL + pgvector knowledge store
- Redis response caching and request rate limiting
- Local Ollama embeddings (mxbai-embed-large) and generation (qwen3:4b-instruct)
- Cited RAG answers with relevance thresholds and safe insufficient-evidence responses
- Citation validation and deterministic output-safety validation
- Prompt-injection detection for user questions and suspicious retrieved evidence
- Secret and narrow PII redaction before storage, chunking, embedding, retrieval, logs, and optional S3 storage
- Markdown, TXT, digital PDF, and DOCX document uploads
- Private, versioned, AES-256-encrypted Amazon S3 mirroring for extracted redacted text
- Short-lived, version-pinned S3 download links issued only after document and role authorization
- Background worker processing across all tenant workspaces
- Amazon Cognito Hosted UI sign-in using OAuth authorization-code flow with PKCE
- Server-side Cognito JWT verification using issuer, audience, token-use, expiry, and JWKS checks
- PostgreSQL-backed organizations, users, memberships, workspaces, and roles
- Roles: admin, manager, and engineer
- Role-aware document visibility: organization and restricted
- Role-aware browser upload controls, with API-side authorization remaining mandatory
- Organization-scoped retrieval, document status, deployment, runbook, cache, chunk, and audit queries
- PostgreSQL audit events correlated through server-generated request IDs
- Safe audit records for authenticated API sessions, RAG outcomes, document operations, rate-limit decisions, prompt-injection denials, and workspace-access denials
- Custom read-only MCP server with approved knowledge, deployment, and runbook access
- Prometheus API/RAG metrics and a local Grafana dashboard
- GitHub Actions checks for API tests, web lint/build, Terraform validation, and committed-secret scanning

## Security model

The browser does not decide authorization.

~~~mermaid
flowchart LR
    Browser["Next.js browser"] -->|OAuth code + PKCE| Cognito["Amazon Cognito Hosted UI"]
    Cognito -->|short-lived access token| Browser

    Browser -->|Bearer token + X-Workspace-Slug| API["FastAPI API"]
    API -->|verify JWT| Cognito
    API -->|user + membership + role check| DB["PostgreSQL + pgvector"]

    API --> Redis["Redis: cache + rate limits"]
    API --> Ollama["Ollama: embeddings + chat"]
    API --> S3["Private S3: redacted extracted text"]

    Worker["Background worker"] --> DB
    Worker --> Ollama

    MCP["Read-only MCP server"] --> API
    Prometheus["Prometheus"] --> API
    Grafana["Grafana"] --> Prometheus
~~~

The X-Workspace-Slug request header selects a workspace; it is not proof of access. The API verifies the Cognito access token, finds the user and membership in PostgreSQL, confirms that membership belongs to the requested workspace's organization, then checks the role and permission. A request to another organization returns a privacy-preserving 404 and creates a safe denial audit event.

## Roles and document access

| Role | Read organization documents | Read restricted documents | Upload or update documents |
|---|---:|---:|---:|
| engineer | Yes | No | No |
| manager | Yes | Yes | Yes |
| admin | Yes | Yes | Yes |

The UI reflects these permissions for usability. The API enforces them, so bypassing the UI does not grant access.

## Document ingestion and retrieval

~~~mermaid
flowchart LR
    Upload["Authenticated upload"] --> Validate["Validate file and authorization"]
    Validate --> Redact["Redact secrets and narrow PII"]
    Redact --> Database["Store document metadata + redacted content"]
    Redact --> S3["Optional private S3 redacted-text mirror"]
    Database --> Worker["Background worker"]
    Worker --> Chunk["Chunk document"]
    Chunk --> Embed["Create Ollama embeddings"]
    Embed --> Search["Organization and role-scoped retrieval"]
    Search --> Answer["Cited, validated answer or safe refusal"]
~~~

The worker processes pending work across all workspaces. Retrieval filters organization and document access level before a response is generated. A cache key includes the caller's access scope, so a broader answer cannot be reused for a less-privileged caller.

## Local setup

### Prerequisites

- Docker Desktop
- Python 3.14 and [uv](https://docs.astral.sh/uv/)
- Node.js and npm
- Ollama
- Optional for S3/Cognito work: AWS CLI, Terraform, and an AWS development account

### Start the local stack

~~~powershell
Copy-Item .env.example .env
Copy-Item apps\web\.env.local.example apps\web\.env.local
docker compose up -d --build
docker compose exec ollama ollama pull mxbai-embed-large
docker compose exec ollama ollama pull qwen3:4b-instruct
~~~

Run migrations, bootstrap the local identity for local-provider development, and ingest the synthetic seed documents:

~~~powershell
cd services\api
uv run alembic upgrade head
uv run python -m scripts.bootstrap_local_identity
uv run python -m scripts.ingest_demo_data --source-dir ../../docs/demo-data
~~~

Start the frontend:

~~~powershell
cd apps\web
npm install
npm run dev
~~~

Open http://localhost:3000. API health and readiness endpoints are available at http://localhost:8000/health and http://localhost:8000/ready.

### Cognito development mode

Terraform creates the Cognito user pool, web client, managed-login domain, and private document-storage controls. Put environment-specific values only in ignored local files:

~~~dotenv
IDENTITY_PROVIDER=cognito
COGNITO_ISSUER=https://cognito-idp.<aws-region>.amazonaws.com/<user-pool-id>
COGNITO_APP_CLIENT_ID=<web-client-id>
~~~

The web app needs matching public values in apps/web/.env.local:

~~~dotenv
NEXT_PUBLIC_COGNITO_ISSUER=https://cognito-idp.<aws-region>.amazonaws.com/<user-pool-id>
NEXT_PUBLIC_COGNITO_CLIENT_ID=<web-client-id>
NEXT_PUBLIC_COGNITO_MANAGED_LOGIN_BASE_URL=https://<domain>.auth.<aws-region>.amazoncognito.com
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
~~~

After creating a Cognito test user, map its stable Cognito sub claim to an application user and workspace membership:

~~~powershell
cd services\api
uv run python -m scripts.bootstrap_cognito_identity <cognito-subject-id> `
  --display-name "Demo Administrator" `
  --role admin
~~~

The API accepts only verified Cognito access tokens that match its configured issuer and app client. It never accepts the browser's chosen role or workspace as authorization.

### Private S3 document storage

When DOCUMENT_STORAGE_BACKEND=s3, the API mirrors only already-redacted extracted UTF-8 text to the configured bucket. The original uploaded binary is not stored in S3 by this feature.

For local Docker development, the Compose configuration may mount the developer's AWS profile read-only so the API can create short-lived S3 links. This is development-only convenience. A deployed workload must use a dedicated least-privilege IAM task role instead of host credentials.

## API highlights

| Route | Purpose |
|---|---|
| POST /api/v1/identity/session | Records a safe audit event after an accepted authenticated session. |
| GET /api/v1/workspaces | Returns the caller's authorized workspaces and roles. |
| POST /api/v1/ask | Returns a cited grounded answer, safe refusal, or guarded validation outcome. |
| GET /api/v1/documents | Lists document status for the active authorized workspace. |
| POST /api/v1/documents | Uploads a document when the caller has documents:write. |
| GET /api/v1/documents/download?source_path=... | Produces an authorized short-lived download link for a redacted S3 object. |
| GET /api/v1/deployments/{service}/{version} | Returns authorized deployment context. |
| GET /api/v1/runbooks/{runbook_name} | Returns authorized runbook context. |
| GET /metrics | Exposes safe Prometheus metrics without tenant or request-ID labels. |

## Quality checks

From the repository root:

~~~powershell
cd services\api
uv run ruff check .
uv run python -m pytest -q

cd ..\..\apps\web
npm run lint
npm run build
npm audit --omit=dev

cd ..\..\infra\terraform
terraform fmt -check
terraform validate
~~~

The latest local API suite completed with **222 passed, 1 deselected**. The live Docker/Ollama end-to-end test remains opt-in because local generation performance depends on the host machine.

## Security boundaries and current limitations

- This is a development learning project, not a production deployment.
- Only synthetic, redacted demonstration data belongs in this repository and its cloud resources.
- A valid citation supports an answer but does not make operational action automatic.
- The product does not restart services, run shell commands, execute arbitrary SQL, mutate AWS resources, or roll back deployments.
- Presigned S3 URLs are sensitive bearer links until they expire. Do not paste them into tickets, chat, commits, or screenshots.
- Cognito and application authorization are implemented for the current local multi-workspace flow, but production hardening still needs dedicated workload roles, secrets management, private networking, WAF, CloudTrail, alerting, retention/deletion policy, and broader security testing.

## Supporting documentation

- [V0.1 release checklist](docs/release/v0.1-release-checklist.md)
- [V0.1 demo script](docs/demo/v0.1-demo-script.md)
- [Security threat model](docs/security/threat-model-v1.md)
- [Versioned roadmap](VERSIONED_ROADMAP.md)
