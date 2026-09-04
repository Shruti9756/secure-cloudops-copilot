# SecureCloudOps Copilot — Threat Model v1

> **Status:** V0.2 local multi-tenant security baseline
>
> **Last reviewed:** 4 September 2026
>
> **Scope:** Local Next.js, FastAPI, PostgreSQL/pgvector, Redis, Ollama, Amazon Cognito, private S3 redacted-text storage, Terraform, and the custom read-only MCP server.
>
> **Important:** This describes verified local-development controls. It does not claim production deployment readiness, database row-level security, or complete cloud-security coverage.

## 1. Purpose

SecureCloudOps Copilot helps engineers investigate incidents using organization-scoped documentation, grounded RAG answers, and controlled read-only MCP capabilities.

This threat model identifies major abuse and failure scenarios, records controls implemented in the current V0.2 development baseline, and makes remaining production work explicit.

The analysis uses:

- **STRIDE:** Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, and Elevation of privilege.
- **OWASP LLM Top 10 lens:** prompt injection, sensitive-information disclosure, improper output handling, excessive agency, vector/embedding weaknesses, misinformation, and unbounded consumption.

## 2. Current data flow

~~~mermaid
flowchart LR
    Browser["Next.js browser"] -->|OAuth code + PKCE| Cognito["Amazon Cognito Hosted UI"]
    Cognito -->|access token| Browser
    Browser -->|Bearer token + workspace selector| API["FastAPI API"]

    API -->|issuer, client, token-use, expiry, signature, JWKS validation| Cognito
    API -->|user, membership, role, organization lookup| Database["PostgreSQL + pgvector"]
    API --> Redis["Redis: rate limit + access-scoped cache"]
    API --> Ollama["Local Ollama: embeddings + chat"]
    API --> S3["Private S3: redacted extracted text"]

    Upload["Authorized upload"] --> Redaction["Secret + narrow PII redaction"]
    Redaction --> Database
    Redaction --> S3
    Worker["Background worker: all workspaces"] --> Database
    Worker --> Ollama

    MCPHost["MCP host"] --> MCP["Custom fixed read-only MCP server"]
    MCP --> API
~~~

## 3. Assets to protect

| Asset | Why it matters |
|---|---|
| Cognito access tokens | Prove a signed-in user's identity until expiry. |
| Users, memberships, organizations, and workspaces | Decide which organization a user may access and what role they hold. |
| Knowledge documents and chunks | Can contain internal operational context or accidental secret/PII uploads. |
| Embeddings and retrieval metadata | Can disclose semantic information about documents. |
| Organization boundary and document access level | A user must never retrieve another organization's sources or documents beyond their role. |
| RAG answer integrity | Incident responders must not receive fabricated, uncited, or unsafe guidance. |
| S3 redacted-text objects and signed links | Private content must remain private; a signed URL is a temporary bearer capability. |
| Audit events | Must support investigation without becoming a duplicate store of questions, answers, tokens, or document bodies. |
| MCP tool boundary | The model must not gain shell, arbitrary SQL, URL, or AWS capabilities. |

## 4. Trust boundaries

| Boundary | Trust level | Security decision |
|---|---|---|
| Browser input and selected workspace | Untrusted | The browser supplies a token and selector; it does not decide authorization. |
| Cognito access token | Cryptographically verifiable input | API checks issuer, client audience, token use, expiry, signature, and JWKS key. |
| Application user and membership record | Authorization source | API maps the Cognito sub to PostgreSQL and verifies organization membership and role. |
| Uploaded or ingested document | Untrusted content | Validate type/size, redact recognized secrets and narrow PII, and treat content as reference data rather than instructions. |
| User question and retrieved evidence | Untrusted text | Detect suspicious injection patterns; do not execute instructions from either source. |
| Ollama response | Untrusted generated output | Require strict Pydantic answer/citation shape validation, validate citations, and run deterministic output-safety checks. |
| PostgreSQL and Redis | Trusted local dependencies | API owns access and query filtering; Redis cache keys include access scope. |
| Private S3 | Privileged external storage | Store only redacted extracted text and issue a version-pinned, short-lived link only after authorization. |
| MCP host/client | Semi-trusted integration boundary | Expose only fixed, validated, read-only capabilities. |

## 5. Security invariants

These rules must remain true as the system evolves:

1. The model and browser do not make authorization decisions.
2. An API request is authorized from a verified Cognito token, database membership, organization, and role.
3. Workspace selection never overrides the caller's organization membership.
4. Retrieval, document status, deployment context, runbook context, chunks, cache, and audit records carry organization scope.
5. An engineer may read organization documents but cannot read restricted documents or write documents; manager and admin may perform those actions.
6. A cache response is keyed by access scope and cannot cross a privilege boundary.
7. A response without sufficient evidence does not call the chat model.
8. A model response is returned only if it matches the strict expected answer-and-citation schema.
9. A grounded response cites only retrieved source identifiers.
10. Recognized secrets and narrow PII are redacted before storage, chunking, embedding, retrieval, logs, or optional S3 mirroring.
11. A presigned S3 URL is created only for an authorized document and is never stored in an audit event.
12. MCP exposes no arbitrary shell commands, SQL, unrestricted URLs, or generic AWS API access.
13. Operational changes always require explicit human approval.

## 6. Threat register

Risk ratings describe the current local baseline, not a production deployment.

| ID | STRIDE / OWASP lens | Threat scenario | Current controls | Remaining risk and next action |
|---|---|---|---|---|
| TM-01 | Tampering / Prompt injection | A question or retrieved document says to ignore rules, reveal data, or restart production. | Prompt-injection detection covers suspicious questions and retrieved evidence. Retrieved content is explicitly contextual, citation validation runs, and deterministic output-safety validation blocks selected dangerous recommendations. | Pattern checks are not complete protection. Expand red-team cases, add claim-level evaluation, and evaluate additional guardrail controls before production. |
| TM-02 | Information disclosure / Sensitive-information disclosure | A document includes a bearer token, AWS credential-like value, email address, phone number, or similar sensitive text. | Ingestion redacts supported secret patterns and narrow PII before database storage, chunking, embedding, worker processing, retrieval, logs, and S3 mirroring. Metadata records only safe count/category information. | Detection is deliberately narrow and cannot find every secret or PII type. Add broader scanning, an approved PII policy, retention/deletion workflows, and upload review. |
| TM-03 | Information disclosure | A caller selects another organization's workspace or tries to retrieve another organization's evidence. | Cognito token is mapped to PostgreSQL membership; organization-scoped query filters apply before retrieval; inaccessible workspace requests return a privacy-preserving 404; denial is audited. | The local database does not yet use row-level security. Add RLS or an equivalent defense-in-depth control, integration tests across more roles, and production monitoring. |
| TM-04 | Elevation of privilege | An engineer bypasses disabled browser controls and posts an upload or requests restricted content directly. | API enforces permissions independent of the UI. Engineers have read-only organization access; document writes and restricted reads require manager or admin role. Denials are audited. | Add explicit permission management, admin review, and fuller role lifecycle controls for production. |
| TM-05 | Information disclosure | A caller downloads a document they cannot access, or a signed link leaks. | Download endpoint performs document, organization, and role checks before generating a short-lived version-pinned link to redacted text only. The link is not persisted in audit metadata. | A signed URL is a bearer link until expiry. Use very short lifetimes, do not log/share it, and consider a proxy download path or additional controls for production. |
| TM-06 | Elevation of privilege / Excessive agency | A model or MCP client attempts shell commands, arbitrary SQL, unrestricted URLs, or AWS actions. | MCP has a fixed allowlist of read-only tools/resources and a fixed-endpoint API adapter. No arbitrary shell, SQL, URL, or AWS path exists. | Add authenticated MCP caller propagation, fuller MCP audit coverage, and dedicated read-only cloud roles before external integrations. |
| TM-07 | Denial of service / Unbounded consumption | Repeated requests exhaust local model capacity or create excessive cost. | Redis fixed-window rate limiting allows 10 requests per 60 seconds; safe responses are cached; Redis failure fails closed for rate limiting; metrics expose safe aggregate request/RAG outcomes. | Add authenticated per-user and per-organization quotas, load shedding, budget alarms, WAF, and dependency-outage exercises. |
| TM-08 | Improper output handling / Misinformation | The model provides malformed output, unsupported claims, bad citations, or unsafe remediation. | Relevance threshold produces safe insufficient-evidence responses; strict Pydantic validation checks the JSON answer/citation shape; citations must match retrieved chunks; output-safety validation blocks selected unsafe actions. | A valid citation does not prove every statement. Expand evaluation, use reviewer workflows for operational decisions, and retain human approval. |
| TM-09 | Spoofing / Repudiation | A user impersonates another user, or a sensitive decision cannot be traced. | Cognito access tokens are verified server-side. Audits record safe actor type/id, request IDs, success/denial states, and non-sensitive metadata without raw questions, answers, tokens, document bodies, or presigned URLs. | Add centralized immutable audit retention, CloudTrail, trace correlation, alerting, and administrator investigation workflows. |
| TM-10 | Supply chain / Configuration tampering | A dependency, image, Terraform change, or leaked configuration weakens the system. | Lock files, Docker local environment, GitHub Actions API/web/Terraform checks, and committed-secret scanning are present. Terraform manages development S3 and Cognito resources. | Add dependency and container scanning, SBOMs, provenance, protected branches, infrastructure review, and secrets management. |

## 7. Current security-test and live evidence

| Evidence | What it proves |
|---|---|
| tests/test_cognito.py, tests/test_cognito_identity.py, and tests/test_authorization.py | Cognito JWT checks and server-side identity/membership authorization behavior. |
| tests/test_workspace_endpoint.py, tests/test_ask_authorization.py, and tests/test_document_upload_authorization.py | Workspace selection, privacy-preserving denials, and API-enforced read/write authorization. |
| tests/test_document_access.py, tests/test_retrieval.py, and tests/test_document_download_endpoint.py | Role-aware document access, organization-scoped retrieval, access-scoped caching, and authorized S3 links. |
| tests/test_prompt_injection.py, tests/test_structured_answer.py, tests/test_safety.py, and tests/test_rag.py | Injection handling, strict structured-output validation, output safety, relevance threshold, and citation validation. |
| tests/test_redaction.py, tests/test_ingestion.py, and tests/test_s3.py | Redaction before persistence and redacted-text S3 storage behavior. |
| tests/test_audit.py, tests/test_ask_endpoint.py, and request-ID tests | Safe, correlated audit metadata for completed, cached, denied, failed, and authenticated-session paths. |
| services/mcp-server/tests/ | Input validation, fixed API boundaries, read-only MCP tools, resources, and prompts. |
| Live local checks | A Cognito NimbusCart administrator received authorized answers/uploads; a SkyForge engineer saw only SkyForge evidence, could not upload, and received an audited denial when attempting cross-workspace write access. |

At this checkpoint, the API suite has **232 passing tests and 1 deselected opt-in test**. The local Docker/Ollama end-to-end test remains opt-in because generation time depends on the development machine.

## 8. Prioritized remaining work

1. **Production identity lifecycle:** Account recovery, user deprovisioning, MFA policy review, role administration, and tenant onboarding/offboarding.
2. **Defense in depth for data isolation:** Database RLS or equivalent, more cross-organization integration tests, and stronger cache invalidation/authorization review.
3. **Cloud workload hardening:** Dedicated workload IAM roles, Secrets Manager, KMS decisions, private networking, WAF, CloudTrail, backup/restore, and alerting.
4. **Broader AI security:** More adversarial evaluation, claim-level grounding review, tool-result injection tests, and a broader PII/secrets policy.
5. **Operational resilience:** Authenticated quotas, load tests, model/dependency outage behavior, dashboards, traces, SLOs, and incident drills.
6. **Release governance:** Protected branches, image/dependency scanning, SBOM/provenance, deployment approval, and documented retention/deletion policies.

## 9. Review rule

Review and update this threat model whenever the project adds:

- a model provider, document format, upload path, or retrieval source;
- a new MCP tool or external integration;
- a user role, permission, or identity provider change;
- a database, cache, S3, or Terraform change;
- an AWS deployment component; or
- a production write-capable action.

A threat model is a living engineering document, not a one-time checklist.
