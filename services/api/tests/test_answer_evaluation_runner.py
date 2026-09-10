from unittest.mock import Mock

import pytest

from app.services.answer_evaluation_runner import (
    AnswerEvaluationCase,
    run_answer_evaluation,
)
from app.services.rag import GroundedAnswer

EXPECTED_SOURCE = "deployments/checkout-2.4.0.md#chunk-0"
DISTRACTOR_SOURCE = "deployments/checkout-2.4.1.md#chunk-0"


def make_grounded_answer(
    *,
    cited_source_identifiers: tuple[str, ...] = (EXPECTED_SOURCE,),
) -> GroundedAnswer:
    """Create one successful synthetic RAG answer."""

    return GroundedAnswer(
        answer_text="The timeout change is a likely hypothesis.",
        embedding_model="test-embedding-model",
        generation_model="test-generation-model",
        query_input_token_count=4,
        prompt_token_count=20,
        completion_token_count=6,
        sources=(Mock(),),
        citation_validation=Mock(
            is_valid=True,
            cited_source_identifiers=cited_source_identifiers,
        ),
        safety_validation=Mock(is_safe=True),
        structured_output_validation_passed=True,
    )


def make_insufficient_evidence_answer() -> GroundedAnswer:
    """Create one synthetic safe abstention."""

    return GroundedAnswer(
        answer_text="I don't have enough evidence to answer safely.",
        embedding_model="test-embedding-model",
        generation_model=None,
        query_input_token_count=3,
        prompt_token_count=None,
        completion_token_count=None,
        sources=(),
        citation_validation=None,
        safety_validation=None,
    )


def test_runner_aggregates_grounded_and_abstention_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    embedding_provider = Mock()
    chat_provider = Mock()
    answers = iter(
        (
            make_grounded_answer(),
            make_insufficient_evidence_answer(),
        )
    )
    captured_questions: list[str] = []

    def fake_answer_grounded_question(**kwargs: object) -> GroundedAnswer:
        captured_questions.append(str(kwargs["question"]))

        assert kwargs["session"] is session
        assert kwargs["embedding_provider"] is embedding_provider
        assert kwargs["chat_provider"] is chat_provider
        assert kwargs["limit"] == 3

        return next(answers)

    monkeypatch.setattr(
        "app.services.answer_evaluation_runner.answer_grounded_question",
        fake_answer_grounded_question,
    )

    report = run_answer_evaluation(
        session=session,
        cases=(
            AnswerEvaluationCase(
                case_id="RAG-EVAL-001",
                category="grounded_answer",
                tenant_slug="nimbuscart",
                question="Why did checkout latency increase?",
                expected_outcome="grounded",
                expected_source_identifiers=(EXPECTED_SOURCE,),
            ),
            AnswerEvaluationCase(
                case_id="RAG-EVAL-002",
                category="insufficient_evidence",
                tenant_slug="nimbuscart",
                question="What Kubernetes version is running?",
                expected_outcome="insufficient_evidence",
                expected_source_identifiers=(),
            ),
        ),
        embedding_provider=embedding_provider,
        chat_provider=chat_provider,
        limit=3,
    )

    assert captured_questions == [
        "Why did checkout latency increase?",
        "What Kubernetes version is running?",
    ]
    assert report.requested_k == 3
    assert report.outcome_accuracy == 1.0
    assert report.citation_correctness_rate == 1.0
    assert report.abstention_correctness_rate == 1.0
    assert report.overall_pass_rate == 1.0
    assert report.total_query_input_tokens == 7
    assert report.total_prompt_tokens == 20
    assert report.total_completion_tokens == 6
    assert report.case_results[0].actual_status == "grounded"
    assert report.case_results[1].actual_status == "insufficient_evidence"


def test_runner_detects_a_valid_but_incorrect_citation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.answer_evaluation_runner.answer_grounded_question",
        lambda **_: make_grounded_answer(cited_source_identifiers=(DISTRACTOR_SOURCE,)),
    )

    report = run_answer_evaluation(
        session=Mock(),
        cases=(
            AnswerEvaluationCase(
                case_id="RAG-EVAL-WRONG-CITATION",
                category="grounded_answer",
                tenant_slug="nimbuscart",
                question="What changed in checkout 2.4.0?",
                expected_outcome="grounded",
                expected_source_identifiers=(EXPECTED_SOURCE,),
            ),
        ),
        embedding_provider=Mock(),
        chat_provider=Mock(),
    )

    assert report.outcome_accuracy == 1.0
    assert report.citation_correctness_rate == 0.0
    assert report.abstention_correctness_rate is None
    assert report.overall_pass_rate == 0.0
    assert report.case_results[0].quality.citation_correctness is False


def test_runner_uses_only_applicable_cases_for_conditional_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.answer_evaluation_runner.answer_grounded_question",
        lambda **_: make_insufficient_evidence_answer(),
    )

    report = run_answer_evaluation(
        session=Mock(),
        cases=(
            AnswerEvaluationCase(
                case_id="RAG-EVAL-ABSTENTION",
                category="insufficient_evidence",
                tenant_slug="nimbuscart",
                question="What unsupported version is deployed?",
                expected_outcome="insufficient_evidence",
                expected_source_identifiers=(),
            ),
        ),
        embedding_provider=Mock(),
        chat_provider=Mock(),
    )

    assert report.citation_correctness_rate is None
    assert report.abstention_correctness_rate == 1.0
    assert report.overall_pass_rate == 1.0


def test_runner_rejects_an_empty_case_list() -> None:
    with pytest.raises(
        ValueError,
        match="At least one answer-evaluation case is required",
    ):
        run_answer_evaluation(
            session=Mock(),
            cases=(),
            embedding_provider=Mock(),
            chat_provider=Mock(),
        )
