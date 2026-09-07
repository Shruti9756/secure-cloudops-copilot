import pytest

from app.services.rank_fusion import (
    DEFAULT_RRF_K,
    fuse_ranked_source_identifiers,
)


def test_rank_fusion_boosts_a_source_found_by_both_retrievers() -> None:
    results = fuse_ranked_source_identifiers(
        semantic_source_identifiers=(
            "runbooks/checkout.md#chunk-0",
            "deployments/checkout.md#chunk-0",
        ),
        lexical_source_identifiers=(
            "deployments/checkout.md#chunk-0",
            "runbooks/checkout.md#chunk-0",
        ),
        limit=3,
    )

    assert results[0].source_identifier == "runbooks/checkout.md#chunk-0"
    assert results[0].semantic_rank == 1
    assert results[0].lexical_rank == 2
    assert results[0].rrf_score == pytest.approx(1 / (DEFAULT_RRF_K + 1) + 1 / (DEFAULT_RRF_K + 2))


def test_rank_fusion_uses_stable_source_identifier_tie_breaking() -> None:
    results = fuse_ranked_source_identifiers(
        semantic_source_identifiers=("runbooks/a.md#chunk-0",),
        lexical_source_identifiers=("runbooks/b.md#chunk-0",),
        limit=2,
    )

    assert [result.source_identifier for result in results] == [
        "runbooks/a.md#chunk-0",
        "runbooks/b.md#chunk-0",
    ]


def test_rank_fusion_deduplicates_sources_without_changing_first_rank() -> None:
    results = fuse_ranked_source_identifiers(
        semantic_source_identifiers=(
            "runbooks/checkout.md#chunk-0",
            "runbooks/checkout.md#chunk-0",
            "deployments/checkout.md#chunk-0",
        ),
        lexical_source_identifiers=(),
        limit=2,
    )

    assert [result.source_identifier for result in results] == [
        "runbooks/checkout.md#chunk-0",
        "deployments/checkout.md#chunk-0",
    ]
    assert results[0].semantic_rank == 1
    assert results[1].semantic_rank == 2


def test_rank_fusion_applies_the_requested_result_limit() -> None:
    results = fuse_ranked_source_identifiers(
        semantic_source_identifiers=(
            "runbooks/checkout.md#chunk-0",
            "deployments/checkout.md#chunk-0",
        ),
        lexical_source_identifiers=("company-overview.md#chunk-0",),
        limit=1,
    )

    assert len(results) == 1


def test_rank_fusion_rejects_invalid_parameters() -> None:
    with pytest.raises(ValueError, match="Fusion limit must be at least 1"):
        fuse_ranked_source_identifiers(
            semantic_source_identifiers=(),
            lexical_source_identifiers=(),
            limit=0,
        )

    with pytest.raises(TypeError, match="RRF k must be an integer"):
        fuse_ranked_source_identifiers(
            semantic_source_identifiers=(),
            lexical_source_identifiers=(),
            limit=1,
            rrf_k=True,
        )

    with pytest.raises(ValueError, match="RRF k must be at least 1"):
        fuse_ranked_source_identifiers(
            semantic_source_identifiers=(),
            lexical_source_identifiers=(),
            limit=1,
            rrf_k=0,
        )
