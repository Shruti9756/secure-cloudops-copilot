from typing import Literal

from app.services.rag import GroundedAnswer

type AnswerStatus = Literal[
    "grounded",
    "insufficient_evidence",
    "structured_output_validation_failed",
    "citation_validation_failed",
    "safety_validation_failed",
]


def get_answer_status(answer: GroundedAnswer) -> AnswerStatus:
    """Map one internal RAG result to a stable client-safe status."""

    if not answer.sources:
        return "insufficient_evidence"

    if answer.structured_output_validation_passed is False:
        return "structured_output_validation_failed"

    if answer.citation_validation is not None and not answer.citation_validation.is_valid:
        return "citation_validation_failed"

    if answer.safety_validation is not None and not answer.safety_validation.is_safe:
        return "safety_validation_failed"

    return "grounded"
