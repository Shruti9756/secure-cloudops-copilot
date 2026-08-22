# SecureCloudOps Copilot

SecureCloudOps Copilot is a security-focused AI assistant for investigating cloud and production incidents from approved engineering knowledge.

It lets an engineering team upload synthetic runbooks, deployment records, Markdown, TXT, digital PDF, and DOCX documents; process them into vector embeddings; and ask grounded questions that return source citations instead of unsupported answers.

> This repository uses only synthetic NimbusCart demonstration data. Never upload real production documents, credentials, customer data, or AWS keys.

## What works today

- Next.js and TypeScript investigation UI
- FastAPI API with OpenAPI documentation
- PostgreSQL + pgvector knowledge store
- Redis response cache and request rate limiting
- Local Ollama embeddings (`mxbai-embed-large`) and generation (`qwen3:4b-instruct`)
- Cited RAG answers with relevance thresholds and safe abstention
- Citation validation and deterministic output-safety validation
- Secret redaction before document storage, chunking, embedding, and retrieval
- Markdown, TXT, digital PDF, and DOCX document uploads
- Background Docker worker for automatic chunking and embedding
- PostgreSQL audit events correlated through server-generated request IDs
- Custom read-only MCP server with approved knowledge, deployment, and runbook access
- Prometheus API/RAG metrics and a local Grafana dashboard
- GitHub Actions checks for API tests, web lint/build, and committed-secret scanning

## Local architecture

```mermaid
flowchart LR
    UI["Next.js web UI"] --> API["FastAPI API"]
    MCP["Custom read-only MCP server"] --> API

    API --> Redis["Redis<br/>cache + rate limits"]
    API --> DB["PostgreSQL + pgvector<br/>documents, chunks, vectors, audits"]

    API --> Ollama["Ollama<br/>embeddings + chat"]
    Worker["Background worker"] --> DB
    Worker --> Ollama

    Prometheus["Prometheus"] --> API
    Grafana["Grafana"] --> Prometheus

    AWS["AWS target<br/>ECS, RDS, S3, Bedrock, Terraform"]:::future

    classDef future fill:#1e293b,color:#cbd5e1,stroke:#64748b;