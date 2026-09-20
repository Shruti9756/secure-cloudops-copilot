from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from app.services.chunking_evaluation import (
    CURRENT_CHUNKING_PROFILE,
    SMALLER_CHUNKING_PROFILE,
)
from app.services.chunking_evaluation_catalog import (
    ChunkingCaseLabels,
    ChunkingLabelCatalog,
)
from app.services.retrieval_evaluation_runner import (
    RetrievalEvaluationCase,
    RetrievalEvaluationReport,
)
from scripts.evaluate_chunking import (
    ChunkingComparisonReport,
    ChunkingProfileEvaluationReport,
    _run_profile_evaluation,
    execute_chunking_comparison,
    run_chunking_comparison,
)


def make_case() -> RetrievalEvaluationCase:
    return RetrievalEvaluationCase(
        case_id="RET-EVAL-001",
        category="deployment_impact",
        tenant_slug="retrieval-evaluation",
        question="Why did checkout latency increase?",
        expected_source_identifiers=("deployments/checkout-2.4.0.md#chunk-0",),
    )


def make_label_catalog() -> ChunkingLabelCatalog:
    return ChunkingLabelCatalog(
        base_catalog=("docs/evaluation/retrieval-eval-cases-v1.json"),
        profile_name="smaller-600-100",
        max_chars=600,
        overlap_chars=100,
        case_labels=(
            ChunkingCaseLabels(
                case_id="RET-EVAL-001",
                expected_source_identifiers=("deployments/checkout-2.4.0.md#chunk-1",),
            ),
        ),
    )


def make_retrieval_report(
    *,
    precision: float = 0.5,
    recall: float = 1.0,
) -> RetrievalEvaluationReport:
    return RetrievalEvaluationReport(
        retrieval_strategy="hybrid",
        requested_k=3,
        case_results=(),
        mean_precision_at_k=precision,
        mean_recall_at_k=recall,
        total_query_input_tokens=10,
        mean_retrieval_duration_ms=5.0,
        p50_retrieval_duration_ms=4.0,
        p95_retrieval_duration_ms=8.0,
    )


def make_profile_report(
    *,
    smaller: bool = False,
) -> ChunkingProfileEvaluationReport:
    profile = SMALLER_CHUNKING_PROFILE if smaller else CURRENT_CHUNKING_PROFILE

    return ChunkingProfileEvaluationReport(
        profile=profile,
        document_count=5,
        chunk_count=12 if smaller else 7,
        document_embedding_input_tokens=200 if smaller else 150,
        retrieval_report=make_retrieval_report(),
    )


def test_profile_evaluation_runs_pipeline_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    ingestion_results = [Mock(), Mock()]
    chunking_results = [
        Mock(chunk_count=2),
        Mock(chunk_count=3),
    ]
    embedding_results = [
        Mock(total_input_tokens=11),
        Mock(total_input_tokens=13),
    ]
    retrieval_report = make_retrieval_report()

    ingest = Mock(return_value=ingestion_results)
    chunk = Mock(return_value=chunking_results)
    embed = Mock(return_value=embedding_results)
    evaluate = Mock(return_value=retrieval_report)

    monkeypatch.setattr(
        "scripts.evaluate_chunking.ingest_directory",
        ingest,
    )
    monkeypatch.setattr(
        "scripts.evaluate_chunking.chunk_pending_documents",
        chunk,
    )
    monkeypatch.setattr(
        "scripts.evaluate_chunking.embed_chunked_documents",
        embed,
    )
    monkeypatch.setattr(
        "scripts.evaluate_chunking.run_retrieval_evaluation",
        evaluate,
    )

    case = make_case()
    provider = Mock()
    source_directory = Path("demo-data")

    report = _run_profile_evaluation(
        session=session,
        source_directory=source_directory,
        profile=CURRENT_CHUNKING_PROFILE,
        tenant_slug="chunk-eval-current-test",
        evaluation_cases=(case,),
        embedding_provider=provider,
    )

    ingest.assert_called_once_with(
        session=session,
        source_directory=source_directory,
        tenant_slug="chunk-eval-current-test",
        tenant_name="Chunk Evaluation current-1200-200",
    )
    chunk.assert_called_once_with(
        session=session,
        tenant_slug="chunk-eval-current-test",
        max_chars=1200,
        overlap_chars=200,
    )
    embed.assert_called_once_with(
        session=session,
        tenant_slug="chunk-eval-current-test",
        provider=provider,
    )
    evaluate.assert_called_once_with(
        session=session,
        cases=(case,),
        embedding_provider=provider,
        strategy="hybrid",
        limit=3,
    )

    assert session.flush.call_count == 3
    session.expire_all.assert_called_once()
    assert report.document_count == 2
    assert report.chunk_count == 5
    assert report.document_embedding_input_tokens == 24


def test_comparison_uses_distinct_tenants_and_profile_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluate_profile = Mock(
        side_effect=[
            make_profile_report(),
            make_profile_report(smaller=True),
        ]
    )
    monkeypatch.setattr(
        "scripts.evaluate_chunking._run_profile_evaluation",
        evaluate_profile,
    )

    comparison = run_chunking_comparison(
        session=Mock(),
        source_directory=Path("demo-data"),
        base_cases=(make_case(),),
        label_catalog=make_label_catalog(),
        embedding_provider=Mock(),
        run_token="abc123",
    )

    current_call = evaluate_profile.call_args_list[0].kwargs
    smaller_call = evaluate_profile.call_args_list[1].kwargs

    assert current_call["tenant_slug"] == ("chunk-eval-current-1200-200-abc123")
    assert smaller_call["tenant_slug"] == ("chunk-eval-smaller-600-100-abc123")
    assert current_call["evaluation_cases"][0].expected_source_identifiers == (
        "deployments/checkout-2.4.0.md#chunk-0",
    )
    assert smaller_call["evaluation_cases"][0].expected_source_identifiers == (
        "deployments/checkout-2.4.0.md#chunk-1",
    )
    assert comparison.current.chunk_count == 7
    assert comparison.smaller.chunk_count == 12


def test_comparison_rejects_labels_for_a_different_profile() -> None:
    mismatched_catalog = replace(
        make_label_catalog(),
        max_chars=601,
    )

    with pytest.raises(
        ValueError,
        match="does not match the smaller profile",
    ):
        run_chunking_comparison(
            session=Mock(),
            source_directory=Path("demo-data"),
            base_cases=(make_case(),),
            label_catalog=mismatched_catalog,
            embedding_provider=Mock(),
            run_token="abc123",
        )


def test_execute_comparison_always_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session

    session_factory = Mock(return_value=session_context)
    expected_report = ChunkingComparisonReport(
        current=make_profile_report(),
        smaller=make_profile_report(smaller=True),
    )
    run_comparison = Mock(return_value=expected_report)

    monkeypatch.setattr(
        "scripts.evaluate_chunking.run_chunking_comparison",
        run_comparison,
    )

    report = execute_chunking_comparison(
        session_factory=session_factory,
        source_directory=Path("demo-data"),
        base_cases=(make_case(),),
        label_catalog=make_label_catalog(),
        embedding_provider=Mock(),
    )

    assert report == expected_report
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_execute_comparison_rolls_back_when_evaluation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session

    session_factory = Mock(return_value=session_context)
    monkeypatch.setattr(
        "scripts.evaluate_chunking.run_chunking_comparison",
        Mock(side_effect=RuntimeError("Embedding provider unavailable")),
    )

    with pytest.raises(
        RuntimeError,
        match="Embedding provider unavailable",
    ):
        execute_chunking_comparison(
            session_factory=session_factory,
            source_directory=Path("demo-data"),
            base_cases=(make_case(),),
            label_catalog=make_label_catalog(),
            embedding_provider=Mock(),
        )

    session.rollback.assert_called_once()
    session.commit.assert_not_called()
