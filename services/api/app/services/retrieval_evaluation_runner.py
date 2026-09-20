from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from sqlalchemy.orm import Session

from app.services.embeddings import EmbeddingProvider
from app.services.hybrid_retrieval import (
    HybridRetrievedChunk,
    retrieve_hybrid_chunks,
)
from app.services.lexical_retrieval import (
    LexicalRetrievedChunk,
    retrieve_lexical_chunks,
)
from app.services.reranked_retrieval import retrieve_reranked_hybrid_chunks
from app.services.retrieval import (
    DEFAULT_RETRIEVAL_LIMIT,
    RetrievedChunk,
    retrieve_relevant_chunks,
)
from app.services.retrieval_evaluation import evaluate_retrieval_at_k

type RetrievalStrategy = Literal[
    "semantic",
    "lexical",
    "hybrid",
    "hybrid-reranked",
]
type EvaluationRetrievedChunk = RetrievedChunk | LexicalRetrievedChunk | HybridRetrievedChunk

SUPPORTED_RETRIEVAL_STRATEGIES: frozenset[RetrievalStrategy] = frozenset(
    {
        "semantic",
        "lexical",
        "hybrid",
        "hybrid-reranked",
    }
)


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    """One synthetic question and its expected evidence sources."""

    case_id: str
    category: str
    tenant_slug: str
    question: str
    expected_source_identifiers: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalEvaluationCaseResult:
    """The retrieval outcome and quality measurements for one benchmark case."""

    case_id: str
    retrieved_source_identifiers: tuple[str, ...]
    matched_source_identifiers: tuple[str, ...]
    precision_at_k: float
    recall_at_k: float
    query_input_token_count: int
    embedding_model: str | None
    retrieval_duration_ms: float


@dataclass(frozen=True)
class RetrievalEvaluationReport:
    """Aggregate retrieval quality for one benchmark run."""

    retrieval_strategy: RetrievalStrategy
    requested_k: int
    case_results: tuple[RetrievalEvaluationCaseResult, ...]
    mean_precision_at_k: float
    mean_recall_at_k: float
    total_query_input_tokens: int
    mean_retrieval_duration_ms: float
    p50_retrieval_duration_ms: float
    p95_retrieval_duration_ms: float


def run_retrieval_evaluation(
    session: Session,
    cases: Sequence[RetrievalEvaluationCase],
    embedding_provider: EmbeddingProvider,
    *,
    strategy: RetrievalStrategy = "semantic",
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
) -> RetrievalEvaluationReport:
    """Run one retrieval strategy against every synthetic evaluation case."""

    if not cases:
        raise ValueError("At least one evaluation case is required")

    if strategy not in SUPPORTED_RETRIEVAL_STRATEGIES:
        raise ValueError("Retrieval strategy must be semantic, lexical, hybrid, or hybrid-reranked")

    case_results = tuple(
        _evaluate_case(
            session=session,
            case=case,
            embedding_provider=embedding_provider,
            strategy=strategy,
            limit=limit,
        )
        for case in cases
    )

    retrieval_durations_ms = tuple(result.retrieval_duration_ms for result in case_results)
    return RetrievalEvaluationReport(
        retrieval_strategy=strategy,
        requested_k=limit,
        case_results=case_results,
        mean_precision_at_k=sum(result.precision_at_k for result in case_results)
        / len(case_results),
        mean_recall_at_k=sum(result.recall_at_k for result in case_results) / len(case_results),
        total_query_input_tokens=sum(result.query_input_token_count for result in case_results),
        mean_retrieval_duration_ms=(sum(retrieval_durations_ms) / len(retrieval_durations_ms)),
        p50_retrieval_duration_ms=_calculate_percentile(
            retrieval_durations_ms,
            0.50,
        ),
        p95_retrieval_duration_ms=_calculate_percentile(
            retrieval_durations_ms,
            0.95,
        ),
    )


def _evaluate_case(
    session: Session,
    case: RetrievalEvaluationCase,
    embedding_provider: EmbeddingProvider,
    strategy: RetrievalStrategy,
    limit: int,
) -> RetrievalEvaluationCaseResult:
    """Run one selected retrieval strategy and measure its evidence matches."""
    # Include query embedding plus database retrieval, fusion, and reranking.
    retrieval_started_at = perf_counter()
    retrieved_chunks: list[EvaluationRetrievedChunk]
    query_input_token_count: int
    embedding_model: str | None

    if strategy == "lexical":
        retrieved_chunks = retrieve_lexical_chunks(
            session=session,
            tenant_slug=case.tenant_slug,
            query=case.question,
            limit=limit,
        )
        query_input_token_count = 0
        embedding_model = None
    else:
        query_embedding = embedding_provider.embed(case.question)

        if strategy == "semantic":
            retrieved_chunks = retrieve_relevant_chunks(
                session=session,
                tenant_slug=case.tenant_slug,
                query_vector=query_embedding.vector,
                embedding_model=query_embedding.model_id,
                limit=limit,
            )
        elif strategy == "hybrid":
            retrieved_chunks = retrieve_hybrid_chunks(
                session=session,
                tenant_slug=case.tenant_slug,
                query=case.question,
                query_vector=query_embedding.vector,
                embedding_model=query_embedding.model_id,
                limit=limit,
            )
        else:
            retrieved_chunks = retrieve_reranked_hybrid_chunks(
                session=session,
                tenant_slug=case.tenant_slug,
                query=case.question,
                query_vector=query_embedding.vector,
                embedding_model=query_embedding.model_id,
                limit=limit,
            )

        query_input_token_count = query_embedding.input_text_token_count
        embedding_model = query_embedding.model_id

    retrieval_duration_ms = (perf_counter() - retrieval_started_at) * 1000
    retrieval_measurement = evaluate_retrieval_at_k(
        expected_source_identifiers=case.expected_source_identifiers,
        retrieved_source_identifiers=tuple(_source_identifier(chunk) for chunk in retrieved_chunks),
        k=limit,
    )

    return RetrievalEvaluationCaseResult(
        case_id=case.case_id,
        retrieved_source_identifiers=retrieval_measurement.retrieved_source_identifiers,
        matched_source_identifiers=retrieval_measurement.matched_source_identifiers,
        precision_at_k=retrieval_measurement.precision_at_k,
        recall_at_k=retrieval_measurement.recall_at_k,
        query_input_token_count=query_input_token_count,
        embedding_model=embedding_model,
        retrieval_duration_ms=retrieval_duration_ms,
    )


def _calculate_percentile(
    values: Sequence[float],
    percentile: float,
) -> float:
    """Calculate a linearly interpolated percentile for measured durations."""

    if not values:
        raise ValueError("Percentile values must not be empty")

    if not 0 <= percentile <= 1:
        raise ValueError("Percentile must be between 0 and 1")

    ordered_values = sorted(values)
    position = (len(ordered_values) - 1) * percentile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered_values) - 1)
    interpolation_weight = position - lower_index

    return (
        ordered_values[lower_index]
        + (ordered_values[upper_index] - ordered_values[lower_index]) * interpolation_weight
    )


def _source_identifier(chunk: EvaluationRetrievedChunk) -> str:
    """Use the same stable document-and-chunk ID across all strategies."""

    return f"{chunk.source_path}#chunk-{chunk.chunk_index}"
