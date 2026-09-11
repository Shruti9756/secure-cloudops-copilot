from collections.abc import Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RetrievalEvaluationReport:
    """Aggregate retrieval quality for one benchmark run."""

    retrieval_strategy: RetrievalStrategy
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

    return RetrievalEvaluationReport(
        retrieval_strategy=strategy,
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
    strategy: RetrievalStrategy,
    limit: int,
) -> RetrievalEvaluationCaseResult:
    """Run one selected retrieval strategy and measure its evidence matches."""

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
    )


def _source_identifier(chunk: EvaluationRetrievedChunk) -> str:
    """Use the same stable document-and-chunk ID across all strategies."""

    return f"{chunk.source_path}#chunk-{chunk.chunk_index}"
