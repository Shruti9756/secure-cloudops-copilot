import pytest

from app.services.answer_evaluation import evaluate_answer_quality

DEPLOYMENT_SOURCE = "deployments/checkout-2.4.0.md#chunk-0"
RUNBOOK_SOURCE = "runbooks/checkout-latency.md#chunk-0"
DISTRACTOR_SOURCE = "deployments/checkout-2.4.1.md#chunk-0"


def test_grounded_answer_passes_with_an_expected_valid_citation() -> None:
    result = evaluate_answer_quality(
        expected_outcome="grounded",
        expected_source_identifiers=(
            DEPLOYMENT_SOURCE,
            RUNBOOK_SOURCE,
        ),
        actual_status="grounded",
        cited_source_identifiers=(DEPLOYMENT_SOURCE,),
        citation_validation_passed=True,
    )

    assert result.outcome_correct is True
    assert result.citation_correctness is True
    assert result.abstention_correctness is None
    assert result.passed is True


def test_grounded_answer_fails_when_it_cites_a_distractor() -> None:
    result = evaluate_answer_quality(
        expected_outcome="grounded",
        expected_source_identifiers=(DEPLOYMENT_SOURCE,),
        actual_status="grounded",
        cited_source_identifiers=(DISTRACTOR_SOURCE,),
        citation_validation_passed=True,
    )

    assert result.outcome_correct is True
    assert result.citation_correctness is False
    assert result.passed is False


def test_grounded_answer_fails_when_citation_validation_failed() -> None:
    result = evaluate_answer_quality(
        expected_outcome="grounded",
        expected_source_identifiers=(DEPLOYMENT_SOURCE,),
        actual_status="grounded",
        cited_source_identifiers=(DEPLOYMENT_SOURCE,),
        citation_validation_passed=False,
    )

    assert result.outcome_correct is True
    assert result.citation_correctness is False
    assert result.passed is False


def test_grounded_case_fails_when_the_system_unnecessarily_abstains() -> None:
    result = evaluate_answer_quality(
        expected_outcome="grounded",
        expected_source_identifiers=(DEPLOYMENT_SOURCE,),
        actual_status="insufficient_evidence",
        cited_source_identifiers=(),
        citation_validation_passed=None,
    )

    assert result.outcome_correct is False
    assert result.citation_correctness is False
    assert result.abstention_correctness is None
    assert result.passed is False


def test_unsupported_question_passes_when_the_system_abstains() -> None:
    result = evaluate_answer_quality(
        expected_outcome="insufficient_evidence",
        expected_source_identifiers=(),
        actual_status="insufficient_evidence",
        cited_source_identifiers=(),
        citation_validation_passed=None,
    )

    assert result.outcome_correct is True
    assert result.citation_correctness is None
    assert result.abstention_correctness is True
    assert result.passed is True


def test_unsupported_question_fails_when_the_system_answers() -> None:
    result = evaluate_answer_quality(
        expected_outcome="insufficient_evidence",
        expected_source_identifiers=(),
        actual_status="grounded",
        cited_source_identifiers=(RUNBOOK_SOURCE,),
        citation_validation_passed=True,
    )

    assert result.outcome_correct is False
    assert result.citation_correctness is None
    assert result.abstention_correctness is False
    assert result.passed is False


def test_inconsistent_benchmark_expectations_are_rejected() -> None:
    with pytest.raises(ValueError, match="Grounded expectations require"):
        evaluate_answer_quality(
            expected_outcome="grounded",
            expected_source_identifiers=(),
            actual_status="grounded",
            cited_source_identifiers=(DEPLOYMENT_SOURCE,),
            citation_validation_passed=True,
        )

    with pytest.raises(
        ValueError,
        match="Insufficient-evidence expectations must not define",
    ):
        evaluate_answer_quality(
            expected_outcome="insufficient_evidence",
            expected_source_identifiers=(DEPLOYMENT_SOURCE,),
            actual_status="insufficient_evidence",
            cited_source_identifiers=(),
            citation_validation_passed=None,
        )
