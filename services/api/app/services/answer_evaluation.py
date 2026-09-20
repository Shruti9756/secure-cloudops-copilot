from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

type ExpectedAnswerOutcome = Literal["grounded", "insufficient_evidence"]
type ActualAnswerStatus = Literal[
    "grounded",
    "insufficient_evidence",
    "structured_output_validation_failed",
    "citation_validation_failed",
    "safety_validation_failed",
]

SUPPORTED_EXPECTED_OUTCOMES = frozenset(
    {
        "grounded",
        "insufficient_evidence",
    }
)

SUPPORTED_ACTUAL_STATUSES = frozenset(
    {
        "grounded",
        "insufficient_evidence",
        "structured_output_validation_failed",
        "citation_validation_failed",
        "safety_validation_failed",
    }
)


@dataclass(frozen=True)
class AnswerQualityEvaluation:
    """Deterministic quality measurements for one RAG answer."""

    expected_outcome: ExpectedAnswerOutcome
    actual_status: ActualAnswerStatus
    outcome_correct: bool
    citation_correctness: bool | None
    abstention_correctness: bool | None
    passed: bool


def evaluate_answer_quality(
    *,
    expected_outcome: ExpectedAnswerOutcome,
    expected_source_identifiers: Collection[str],
    actual_status: ActualAnswerStatus,
    cited_source_identifiers: Collection[str],
    citation_validation_passed: bool | None,
) -> AnswerQualityEvaluation:
    """Compare one actual RAG outcome with its pre-labeled expectation."""

    if expected_outcome not in SUPPORTED_EXPECTED_OUTCOMES:
        raise ValueError("Expected answer outcome must be grounded or insufficient_evidence")

    if actual_status not in SUPPORTED_ACTUAL_STATUSES:
        raise ValueError("Actual answer status is not supported")

    if citation_validation_passed is not None and not isinstance(
        citation_validation_passed,
        bool,
    ):
        raise TypeError("citation_validation_passed must be a boolean or None")

    expected_sources = _normalize_source_identifiers(
        expected_source_identifiers,
        field_name="Expected source identifiers",
    )
    cited_sources = _normalize_source_identifiers(
        cited_source_identifiers,
        field_name="Cited source identifiers",
    )

    if expected_outcome == "grounded":
        if not expected_sources:
            raise ValueError(
                "Grounded expectations require at least one expected source identifier"
            )

        outcome_correct = actual_status == "grounded"
        expected_source_set = frozenset(expected_sources)
        cited_source_set = frozenset(cited_sources)

        citation_correctness = (
            outcome_correct
            and citation_validation_passed is True
            and bool(cited_source_set)
            and cited_source_set.issubset(expected_source_set)
        )

        return AnswerQualityEvaluation(
            expected_outcome=expected_outcome,
            actual_status=actual_status,
            outcome_correct=outcome_correct,
            citation_correctness=citation_correctness,
            abstention_correctness=None,
            passed=outcome_correct and citation_correctness,
        )

    if expected_sources:
        raise ValueError("Insufficient-evidence expectations must not define expected sources")

    outcome_correct = actual_status == "insufficient_evidence"
    abstention_correctness = (
        outcome_correct and not cited_sources and citation_validation_passed is None
    )

    return AnswerQualityEvaluation(
        expected_outcome=expected_outcome,
        actual_status=actual_status,
        outcome_correct=outcome_correct,
        citation_correctness=None,
        abstention_correctness=abstention_correctness,
        passed=outcome_correct and abstention_correctness,
    )


def _normalize_source_identifiers(
    source_identifiers: Collection[str],
    *,
    field_name: str,
) -> tuple[str, ...]:
    """Validate, trim, and deduplicate stable source identifiers."""

    if isinstance(source_identifiers, str):
        raise TypeError(f"{field_name} must be a collection of strings")

    normalized_sources: list[str] = []

    for source_identifier in source_identifiers:
        if not isinstance(source_identifier, str):
            raise TypeError(f"{field_name} must contain only strings")

        normalized_source = source_identifier.strip()

        if not normalized_source:
            raise ValueError(f"{field_name} must not contain empty values")

        normalized_sources.append(normalized_source)

    return tuple(dict.fromkeys(normalized_sources))
