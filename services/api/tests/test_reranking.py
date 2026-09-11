import pytest

from app.services.reranking import (
    RerankingCandidate,
    rerank_candidates,
)


def test_reranker_promotes_exact_version_metadata() -> None:
    results = rerank_candidates(
        "Which idle timeout did checkout version 2.4.1 restore?",
        (
            RerankingCandidate(
                source_identifier="deployments/checkout-2.4.0.md#chunk-0",
                search_text=(
                    "Deployment checkout 2.4.0 changed the PostgreSQL idle timeout to 5 seconds."
                ),
                base_score=0.0330,
            ),
            RerankingCandidate(
                source_identifier="deployments/checkout-2.4.1.md#chunk-0",
                search_text=(
                    "Deployment checkout 2.4.1 restored the PostgreSQL idle timeout to 120 seconds."
                ),
                base_score=0.0328,
            ),
        ),
        limit=2,
    )

    assert results[0].source_identifier == ("deployments/checkout-2.4.1.md#chunk-0")
    assert results[0].normalized_bm25_score == 1.0
    assert results[0].rerank_score > results[1].rerank_score

def test_reranker_preserves_fusion_order_for_generic_query() -> None:
    results = rerank_candidates(
        "Why did checkout latency increase after the deployment?",
        (
            RerankingCandidate(
                source_identifier="runbooks/checkout.md#chunk-0",
                search_text="Checkout latency investigation runbook.",
                base_score=0.0340,
            ),
            RerankingCandidate(
                source_identifier="deployments/latest.md#chunk-0",
                search_text=(
                    "Why checkout latency increased after the deployment."
                ),
                base_score=0.0339,
            ),
        ),
        limit=2,
    )

    assert results[0].source_identifier == "runbooks/checkout.md#chunk-0"
    assert all(
        result.normalized_bm25_score == 0.0
        for result in results
    )

def test_reranker_keeps_stronger_base_score_when_text_scores_are_equal() -> None:
    results = rerank_candidates(
        "checkout latency",
        (
            RerankingCandidate(
                source_identifier="runbooks/first.md#chunk-0",
                search_text="checkout latency",
                base_score=0.04,
            ),
            RerankingCandidate(
                source_identifier="runbooks/second.md#chunk-0",
                search_text="checkout latency",
                base_score=0.03,
            ),
        ),
        limit=2,
    )

    assert results[0].source_identifier == "runbooks/first.md#chunk-0"


def test_reranker_applies_the_requested_limit() -> None:
    results = rerank_candidates(
        "checkout latency",
        (
            RerankingCandidate(
                source_identifier="runbooks/first.md#chunk-0",
                search_text="checkout latency investigation",
                base_score=0.04,
            ),
            RerankingCandidate(
                source_identifier="runbooks/second.md#chunk-0",
                search_text="checkout latency response",
                base_score=0.03,
            ),
        ),
        limit=1,
    )

    assert len(results) == 1


def test_reranker_returns_no_results_for_no_candidates() -> None:
    assert rerank_candidates("checkout latency", (), limit=3) == ()


def test_reranker_rejects_invalid_arguments() -> None:
    with pytest.raises(
        ValueError,
        match="Reranking query must contain at least one searchable term",
    ):
        rerank_candidates("!!!", (), limit=3)

    with pytest.raises(ValueError, match="Reranking limit must be at least 1"):
        rerank_candidates("checkout", (), limit=0)

    with pytest.raises(
        ValueError,
        match="BM25 reranking weight must be finite and non-negative",
    ):
        rerank_candidates("checkout", (), limit=1, bm25_weight=-0.1)
