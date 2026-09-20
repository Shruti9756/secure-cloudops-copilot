import pytest

from app.services.retrieval_evaluation import evaluate_retrieval_at_k


def test_evaluate_retrieval_at_k_measures_precision_and_recall() -> None:
    result = evaluate_retrieval_at_k(
        expected_source_identifiers=(
            "deployments/checkout-2.4.0.md#chunk-0",
            "runbooks/checkout-latency.md#chunk-0",
        ),
        retrieved_source_identifiers=(
            "company-overview.md#chunk-0",
            "deployments/checkout-2.4.0.md#chunk-0",
            "runbooks/checkout-latency.md#chunk-0",
        ),
        k=2,
    )

    assert result.requested_k == 2
    assert result.retrieved_source_identifiers == (
        "company-overview.md#chunk-0",
        "deployments/checkout-2.4.0.md#chunk-0",
    )
    assert result.matched_source_identifiers == ("deployments/checkout-2.4.0.md#chunk-0",)
    assert result.precision_at_k == 0.5
    assert result.recall_at_k == 0.5


def test_evaluate_retrieval_at_k_deduplicates_retrieved_sources() -> None:
    result = evaluate_retrieval_at_k(
        expected_source_identifiers=(
            "deployments/checkout-2.4.0.md#chunk-0",
            "runbooks/checkout-latency.md#chunk-0",
        ),
        retrieved_source_identifiers=(
            "deployments/checkout-2.4.0.md#chunk-0",
            "deployments/checkout-2.4.0.md#chunk-0",
            "runbooks/checkout-latency.md#chunk-0",
        ),
        k=2,
    )

    assert result.retrieved_source_identifiers == (
        "deployments/checkout-2.4.0.md#chunk-0",
        "runbooks/checkout-latency.md#chunk-0",
    )
    assert result.precision_at_k == 1.0
    assert result.recall_at_k == 1.0


def test_evaluate_retrieval_at_k_handles_no_retrieved_sources() -> None:
    result = evaluate_retrieval_at_k(
        expected_source_identifiers=("runbooks/checkout-latency.md#chunk-0",),
        retrieved_source_identifiers=(),
        k=3,
    )

    assert result.matched_source_identifiers == ()
    assert result.precision_at_k == 0.0
    assert result.recall_at_k == 0.0


def test_evaluate_retrieval_at_k_rejects_an_empty_expected_source_set() -> None:
    with pytest.raises(ValueError, match="Expected source identifiers must not be empty"):
        evaluate_retrieval_at_k(
            expected_source_identifiers=(),
            retrieved_source_identifiers=("runbooks/checkout-latency.md#chunk-0",),
            k=1,
        )


def test_evaluate_retrieval_at_k_rejects_an_invalid_k() -> None:
    with pytest.raises(ValueError, match="k must be at least 1"):
        evaluate_retrieval_at_k(
            expected_source_identifiers=("runbooks/checkout-latency.md#chunk-0",),
            retrieved_source_identifiers=(),
            k=0,
        )
