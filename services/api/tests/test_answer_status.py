from unittest.mock import Mock

from app.services.answer_status import get_answer_status
from app.services.rag import GroundedAnswer


def make_answer(
    *,
    has_sources: bool = True,
    structured_output_valid: bool | None = True,
    citation_valid: bool | None = True,
    safety_valid: bool | None = True,
) -> GroundedAnswer:
    """Create one controlled RAG result for status-classification tests."""

    return GroundedAnswer(
        answer_text="Synthetic answer.",
        embedding_model="test-embedding-model",
        generation_model="test-generation-model",
        query_input_token_count=3,
        prompt_token_count=10,
        completion_token_count=5,
        sources=(Mock(),) if has_sources else (),
        citation_validation=(Mock(is_valid=citation_valid) if citation_valid is not None else None),
        safety_validation=(Mock(is_safe=safety_valid) if safety_valid is not None else None),
        structured_output_validation_passed=structured_output_valid,
    )


def test_answer_without_sources_is_insufficient_evidence() -> None:
    answer = make_answer(
        has_sources=False,
        structured_output_valid=None,
        citation_valid=None,
        safety_valid=None,
    )

    assert get_answer_status(answer) == "insufficient_evidence"


def test_invalid_structured_output_has_its_own_status() -> None:
    answer = make_answer(
        structured_output_valid=False,
        citation_valid=None,
        safety_valid=None,
    )

    assert get_answer_status(answer) == "structured_output_validation_failed"


def test_invalid_citation_has_its_own_status() -> None:
    answer = make_answer(citation_valid=False)

    assert get_answer_status(answer) == "citation_validation_failed"


def test_unsafe_answer_has_its_own_status() -> None:
    answer = make_answer(safety_valid=False)

    assert get_answer_status(answer) == "safety_validation_failed"


def test_answer_passing_all_checks_is_grounded() -> None:
    answer = make_answer()

    assert get_answer_status(answer) == "grounded"
