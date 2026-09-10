from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.answer_evaluation import (
    AnswerQualityEvaluation,
    ExpectedAnswerOutcome,
    evaluate_answer_quality,
)
from app.services.answer_status import AnswerStatus, get_answer_status
from app.services.chat import ChatProvider
from app.services.embeddings import EmbeddingProvider
from app.services.rag import answer_grounded_question
from app.services.retrieval import DEFAULT_RETRIEVAL_LIMIT


@dataclass(frozen=True)
class AnswerEvaluationCase:
    """One question and its pre-labeled expected RAG outcome."""

    case_id: str
    category: str
    tenant_slug: str
    question: str
    expected_outcome: ExpectedAnswerOutcome
    expected_source_identifiers: tuple[str, ...]


@dataclass(frozen=True)
class AnswerEvaluationCaseResult:
    """One actual RAG answer and its deterministic quality evaluation."""

    case_id: str
    category: str
    actual_status: AnswerStatus
    cited_source_identifiers: tuple[str, ...]
    quality: AnswerQualityEvaluation
    query_input_token_count: int
    prompt_token_count: int | None
    completion_token_count: int | None


@dataclass(frozen=True)
class AnswerEvaluationReport:
    """Aggregate answer-quality measurements for one benchmark run."""

    requested_k: int
    case_results: tuple[AnswerEvaluationCaseResult, ...]
    outcome_accuracy: float
    citation_correctness_rate: float | None
    abstention_correctness_rate: float | None
    overall_pass_rate: float
    total_query_input_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int


def run_answer_evaluation(
    session: Session,
    cases: Sequence[AnswerEvaluationCase],
    embedding_provider: EmbeddingProvider,
    chat_provider: ChatProvider,
    *,
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
) -> AnswerEvaluationReport:
    """Run the real RAG service and score every pre-labeled case."""

    if not cases:
        raise ValueError("At least one answer-evaluation case is required")

    case_results = tuple(
        _evaluate_case(
            session=session,
            case=case,
            embedding_provider=embedding_provider,
            chat_provider=chat_provider,
            limit=limit,
        )
        for case in cases
    )

    citation_results = tuple(
        result.quality.citation_correctness
        for result in case_results
        if result.quality.citation_correctness is not None
    )
    abstention_results = tuple(
        result.quality.abstention_correctness
        for result in case_results
        if result.quality.abstention_correctness is not None
    )

    return AnswerEvaluationReport(
        requested_k=limit,
        case_results=case_results,
        outcome_accuracy=(
            sum(result.quality.outcome_correct for result in case_results) / len(case_results)
        ),
        citation_correctness_rate=_optional_boolean_rate(citation_results),
        abstention_correctness_rate=_optional_boolean_rate(abstention_results),
        overall_pass_rate=(
            sum(result.quality.passed for result in case_results) / len(case_results)
        ),
        total_query_input_tokens=sum(result.query_input_token_count for result in case_results),
        total_prompt_tokens=sum(result.prompt_token_count or 0 for result in case_results),
        total_completion_tokens=sum(result.completion_token_count or 0 for result in case_results),
    )


def _evaluate_case(
    *,
    session: Session,
    case: AnswerEvaluationCase,
    embedding_provider: EmbeddingProvider,
    chat_provider: ChatProvider,
    limit: int,
) -> AnswerEvaluationCaseResult:
    """Execute and score one answer-evaluation case."""

    answer = answer_grounded_question(
        session=session,
        tenant_slug=case.tenant_slug,
        question=case.question,
        embedding_provider=embedding_provider,
        chat_provider=chat_provider,
        limit=limit,
    )
    actual_status = get_answer_status(answer)
    citation_validation = answer.citation_validation
    cited_source_identifiers = (
        citation_validation.cited_source_identifiers if citation_validation is not None else ()
    )

    quality = evaluate_answer_quality(
        expected_outcome=case.expected_outcome,
        expected_source_identifiers=case.expected_source_identifiers,
        actual_status=actual_status,
        cited_source_identifiers=cited_source_identifiers,
        citation_validation_passed=(
            citation_validation.is_valid if citation_validation is not None else None
        ),
    )

    return AnswerEvaluationCaseResult(
        case_id=case.case_id,
        category=case.category,
        actual_status=actual_status,
        cited_source_identifiers=cited_source_identifiers,
        quality=quality,
        query_input_token_count=answer.query_input_token_count,
        prompt_token_count=answer.prompt_token_count,
        completion_token_count=answer.completion_token_count,
    )


def _optional_boolean_rate(values: Sequence[bool]) -> float | None:
    """Return a rate for applicable cases, or None when none apply."""

    if not values:
        return None

    return sum(values) / len(values)
