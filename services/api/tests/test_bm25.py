import pytest

from app.services.bm25 import rank_bm25_documents, tokenize_bm25


def test_tokenize_bm25_preserves_incident_ids_and_versions() -> None:
    assert tokenize_bm25("SKYFORGE-ONLY-INCIDENT-2026 uses checkout-2.4.0") == (
        "skyforge-only-incident-2026",
        "uses",
        "checkout-2.4.0",
    )


def test_bm25_ranks_a_document_with_a_rare_exact_incident_id_first() -> None:
    results = rank_bm25_documents(
        "What does SKYFORGE-ONLY-INCIDENT-2026 mean?",
        {
            "runbooks/skyforge.md#chunk-0": (
                "When SKYFORGE-ONLY-INCIDENT-2026 appears, inspect the "
                "SkyForge connection-pool dashboard."
            ),
            "runbooks/checkout.md#chunk-0": ("Investigate checkout connection-pool behavior."),
            "company-overview.md#chunk-0": "SkyForge operates a checkout platform.",
        },
        limit=3,
    )

    assert results[0].source_identifier == "runbooks/skyforge.md#chunk-0"
    assert results[0].score > 0


def test_bm25_is_case_insensitive_and_returns_only_matching_documents() -> None:
    results = rank_bm25_documents(
        "REDIS eviction",
        {
            "runbooks/checkout.md#chunk-1": (
                "If Redis eviction count rises, inspect the eviction policy."
            ),
            "deployments/checkout.md#chunk-0": (
                "The PostgreSQL connection-pool idle timeout changed."
            ),
        },
        limit=3,
    )

    assert results == (results[0],)
    assert results[0].source_identifier == "runbooks/checkout.md#chunk-1"


def test_bm25_returns_no_results_when_no_document_contains_query_terms() -> None:
    results = rank_bm25_documents(
        "unrelated-incident-999",
        {
            "runbooks/checkout.md#chunk-0": "Inspect checkout latency signals.",
        },
        limit=3,
    )

    assert results == ()


def test_bm25_rejects_invalid_query_and_limit() -> None:
    with pytest.raises(
        ValueError,
        match="BM25 query must contain at least one searchable term",
    ):
        rank_bm25_documents(
            "!!!",
            {"runbooks/checkout.md#chunk-0": "Checkout latency guidance."},
            limit=3,
        )

    with pytest.raises(TypeError, match="BM25 limit must be an integer"):
        rank_bm25_documents(
            "checkout",
            {"runbooks/checkout.md#chunk-0": "Checkout latency guidance."},
            limit=True,
        )
