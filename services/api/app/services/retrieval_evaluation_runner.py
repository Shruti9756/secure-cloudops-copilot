from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.embeddings import EmbeddingProvider
from app.services.retrieval import (
    DEFAULT_RETRIEVAL_LIMIT,
    RetrievedChunk,
    retrieve_relevant_chunks,
)
from app.services.retrieval_evaluation import evaluate_retrieval_at_k


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
    embedding_model: str


@dataclass(frozen=True)
class RetrievalEvaluationReport:
    """Aggregate retrieval quality for one benchmark run."""

    requested_k: int
    case_results: tuple[RetrievalEvaluationCaseResult, ...]
    mean_precision_at_k: float
    mean_recall_at_k: float
    total_query_input_tokens: int


def run_retrieval_evaluation(
    session: Session,
    cases: Sequence[RetrievalEvaluationCase],
    embedding_provider: EmbeddingProvider,
    *,
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
) -> RetrievalEvaluationReport:
    """Run real embedding and retrieval for every synthetic evaluation case."""

    if not cases:
        raise ValueError("At least one evaluation case is required")

    case_results = tuple(
        _evaluate_case(
            session=session,
            case=case,
            embedding_provider=embedding_provider,
            limit=limit,
        )
        for case in cases
    )

    return RetrievalEvaluationReport(
        requested_k=limit,
        case_results=case_results,
        mean_precision_at_k=sum(result.precision_at_k for result in case_results)
        / len(case_results),
        mean_recall_at_k=sum(result.recall_at_k for result in case_results) / len(case_results),
        total_query_input_tokens=sum(result.query_input_token_count for result in case_results),
    )


def _evaluate_case(
    session: Session,
    case: RetrievalEvaluationCase,
    embedding_provider: EmbeddingProvider,
    limit: int,
) -> RetrievalEvaluationCaseResult:
    """Embed one benchmark question, retrieve evidence, and measure it."""

    query_embedding = embedding_provider.embed(case.question)
    retrieved_chunks = retrieve_relevant_chunks(
        session=session,
        tenant_slug=case.tenant_slug,
        query_vector=query_embedding.vector,
        embedding_model=query_embedding.model_id,
        limit=limit,
    )
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
        query_input_token_count=query_embedding.input_text_token_count,
        embedding_model=query_embedding.model_id,
    )


def _source_identifier(chunk: RetrievedChunk) -> str:
    """Use the same stable document-and-chunk identifier as the benchmark catalog."""

    return f"{chunk.source_path}#chunk-{chunk.chunk_index}"
