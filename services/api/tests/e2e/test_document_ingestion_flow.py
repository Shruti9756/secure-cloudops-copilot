"""Live E2E proof for document upload, worker processing, and semantic retrieval."""

import os
import time
from uuid import uuid4

import httpx
import pytest

from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.services.retrieval import retrieve_relevant_chunks

# This test calls the real Docker API instead of importing FastAPI directly.
API_BASE_URL = os.getenv("E2E_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# The Docker worker polls every five seconds. Ninety seconds leaves time for processing.
WORKER_WAIT_TIMEOUT_SECONDS = int(os.getenv("E2E_WORKER_WAIT_TIMEOUT_SECONDS", "90"))
WORKER_POLL_INTERVAL_SECONDS = 2

# Normal pytest and GitHub Actions skip this live Docker-dependent test.
pytestmark = pytest.mark.e2e


def wait_until_document_is_embedded(
    client: httpx.Client,
    *,
    source_path: str,
) -> None:
    """Poll the public status API until the real worker finishes processing."""
    deadline = time.monotonic() + WORKER_WAIT_TIMEOUT_SECONDS
    last_observed_status = "not listed yet"

    while time.monotonic() < deadline:
        status_response = client.get("/api/v1/documents")
        assert status_response.status_code == 200, status_response.text

        matching_document = next(
            (
                document
                for document in status_response.json()["documents"]
                if document["source_path"] == source_path
            ),
            None,
        )

        if matching_document is not None:
            last_observed_status = matching_document["ingestion_status"]

            if last_observed_status == "embedded":
                return

        time.sleep(WORKER_POLL_INTERVAL_SECONDS)

    raise AssertionError(
        "The uploaded document did not reach embedded status within "
        f"{WORKER_WAIT_TIMEOUT_SECONDS} seconds. "
        f"Last observed status: {last_observed_status!r}"
    )


def test_upload_worker_embedding_and_tenant_scoped_retrieval_flow() -> None:
    """Prove upload, automatic processing, and real vector retrieval end to end."""
    run_id = uuid4().hex

    # A stable path avoids cluttering local PostgreSQL with a new test document every run.
    # The unique marker changes the content, forcing the worker to reprocess this document.
    filename = "e2e-flow.md"
    source_path = "uploads/e2e-flow.md"
    incident_marker = f"E2E-CONNECTION-POOL-MARKER-{run_id}"

    document_content = (
        "# E2E Worker Verification\n\n"
        f"Incident marker: {incident_marker}\n\n"
        "When this exact incident marker appears, inspect the PostgreSQL "
        "connection-pool idle timeout and the connection recreation rate.\n"
    )
    question = f"What should I inspect when incident marker {incident_marker} appears?"

    # Upload and worker status use the actual public HTTP API.
    with httpx.Client(
        base_url=API_BASE_URL,
        timeout=httpx.Timeout(timeout=30.0, connect=5.0),
    ) as client:
        readiness_response = client.get("/ready")
        assert readiness_response.status_code == 200, readiness_response.text
        assert readiness_response.json()["status"] == "ready"

        upload_response = client.post(
            "/api/v1/documents",
            files={
                "uploaded_file": (
                    filename,
                    document_content.encode("utf-8"),
                    "text/markdown",
                )
            },
        )

        assert upload_response.status_code == 200, upload_response.text

        upload_payload = upload_response.json()

        assert upload_payload["status"] == "accepted"
        # The first run creates it; later runs update it with a new unique marker.
        assert upload_payload["action"] in {"created", "updated"}
        assert upload_payload["tenant"] == "nimbuscart"
        assert upload_payload["source_path"] == source_path

        wait_until_document_is_embedded(client, source_path=source_path)

    # Use the same real embedding client and pgvector retrieval service as RAG.
    embedding_provider = OllamaEmbeddingClient()
    query_embedding = embedding_provider.embed(question)
    session_factory = get_session_factory()

    with session_factory() as session:
        retrieved_chunks = retrieve_relevant_chunks(
            session=session,
            tenant_slug="nimbuscart",
            query_vector=query_embedding.vector,
            embedding_model=query_embedding.model_id,
            limit=1,
        )

    # The only acceptable top result is the newly processed synthetic document.
    assert len(retrieved_chunks) == 1

    retrieved_chunk = retrieved_chunks[0]

    assert retrieved_chunk.source_path == source_path
    assert retrieved_chunk.document_title == "E2E Worker Verification"
    assert retrieved_chunk.chunk_index == 0
    assert incident_marker in retrieved_chunk.content
    assert 0 <= retrieved_chunk.cosine_distance <= 0.40
