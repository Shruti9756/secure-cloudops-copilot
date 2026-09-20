import json
from pathlib import Path

import pytest

from app.services.answer_evaluation import AnswerQualityEvaluation
from app.services.answer_evaluation_runner import (
    AnswerEvaluationCase,
    AnswerEvaluationCaseResult,
    AnswerEvaluationReport,
)
from scripts.evaluate_answers import (
    DEFAULT_CATALOG_PATH,
    load_answer_evaluation_catalog,
    parse_arguments,
    print_answer_evaluation_report,
    select_answer_evaluation_cases,
)


def make_case(
    *,
    case_id: str = "ANSWER-EVAL-001",
    expected_outcome: str = "grounded",
    expected_source_identifiers: list[str] | None = None,
) -> dict[str, object]:
    """Create one synthetic JSON catalog case."""

    if expected_source_identifiers is None:
        expected_source_identifiers = ["deployments/checkout-2.4.0.md#chunk-0"]

    return {
        "id": case_id,
        "category": expected_outcome,
        "tenant": "retrieval-evaluation",
        "question": "Why did checkout latency increase?",
        "expected_outcome": expected_outcome,
        "expected_source_identifiers": expected_source_identifiers,
    }


def write_catalog(
    catalog_path: Path,
    *,
    cases: list[dict[str, object]],
    default_limit: int = 3,
) -> None:
    """Write a temporary answer-evaluation catalog."""

    catalog_path.write_text(
        json.dumps(
            {
                "suite_name": "SecureCloudOps Answer Evaluation Cases",
                "suite_version": "v1",
                "default_retrieval_limit": default_limit,
                "cases": cases,
            }
        ),
        encoding="utf-8",
    )


def test_parse_arguments_uses_the_versioned_catalog_by_default() -> None:
    args = parse_arguments(())

    assert args.catalog == DEFAULT_CATALOG_PATH
    assert args.limit is None
    assert args.case_ids is None


def test_parse_arguments_accepts_a_custom_catalog_and_limit() -> None:
    args = parse_arguments(
        (
            "--catalog",
            "custom-answer-cases.json",
            "--limit",
            "2",
            "--case-id",
            "ANSWER-EVAL-004",
            "--case-id",
            "ANSWER-EVAL-002",
        )
    )

    assert args.catalog == Path("custom-answer-cases.json")
    assert args.limit == 2
    assert args.case_ids == [
        "ANSWER-EVAL-004",
        "ANSWER-EVAL-002",
    ]


def test_select_answer_evaluation_cases_preserves_requested_order() -> None:
    first_case = AnswerEvaluationCase(
        case_id="ANSWER-EVAL-001",
        category="grounded_answer",
        tenant_slug="retrieval-evaluation",
        question="First question?",
        expected_outcome="grounded",
        expected_source_identifiers=("deployments/checkout-2.4.0.md#chunk-0",),
    )
    second_case = AnswerEvaluationCase(
        case_id="ANSWER-EVAL-002",
        category="insufficient_evidence",
        tenant_slug="retrieval-evaluation",
        question="Second question?",
        expected_outcome="insufficient_evidence",
        expected_source_identifiers=(),
    )

    selected_cases = select_answer_evaluation_cases(
        (first_case, second_case),
        ("ANSWER-EVAL-002", "ANSWER-EVAL-001"),
    )

    assert selected_cases == (second_case, first_case)


def test_select_answer_evaluation_cases_rejects_an_unknown_id() -> None:
    case = AnswerEvaluationCase(
        case_id="ANSWER-EVAL-001",
        category="grounded_answer",
        tenant_slug="retrieval-evaluation",
        question="A question?",
        expected_outcome="grounded",
        expected_source_identifiers=("deployments/checkout-2.4.0.md#chunk-0",),
    )

    with pytest.raises(
        ValueError,
        match="Unknown answer-evaluation case ID",
    ):
        select_answer_evaluation_cases(
            (case,),
            ("ANSWER-EVAL-999",),
        )


def test_select_answer_evaluation_cases_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="must not contain duplicates"):
        select_answer_evaluation_cases(
            (),
            ("ANSWER-EVAL-001", "ANSWER-EVAL-001"),
        )


@pytest.mark.parametrize("limit", ("0", "11"))
def test_parse_arguments_rejects_an_out_of_range_limit(limit: str) -> None:
    with pytest.raises(SystemExit):
        parse_arguments(("--limit", limit))


def test_load_answer_evaluation_catalog_returns_typed_cases(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "answer-cases.json"
    write_catalog(
        catalog_path,
        cases=[
            make_case(),
            make_case(
                case_id="ANSWER-EVAL-002",
                expected_outcome="insufficient_evidence",
                expected_source_identifiers=[],
            ),
        ],
    )

    default_limit, cases = load_answer_evaluation_catalog(catalog_path)

    assert default_limit == 3
    assert cases == (
        AnswerEvaluationCase(
            case_id="ANSWER-EVAL-001",
            category="grounded",
            tenant_slug="retrieval-evaluation",
            question="Why did checkout latency increase?",
            expected_outcome="grounded",
            expected_source_identifiers=("deployments/checkout-2.4.0.md#chunk-0",),
        ),
        AnswerEvaluationCase(
            case_id="ANSWER-EVAL-002",
            category="insufficient_evidence",
            tenant_slug="retrieval-evaluation",
            question="Why did checkout latency increase?",
            expected_outcome="insufficient_evidence",
            expected_source_identifiers=(),
        ),
    )


def test_load_answer_evaluation_catalog_rejects_an_unsupported_outcome(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "answer-cases.json"
    write_catalog(
        catalog_path,
        cases=[
            make_case(expected_outcome="maybe_grounded"),
        ],
    )

    with pytest.raises(
        ValueError,
        match="must be grounded or insufficient_evidence",
    ):
        load_answer_evaluation_catalog(catalog_path)


@pytest.mark.parametrize(
    ("expected_outcome", "expected_sources", "error_message"),
    [
        (
            "grounded",
            [],
            "must define expected source identifiers",
        ),
        (
            "insufficient_evidence",
            ["deployments/checkout-2.4.0.md#chunk-0"],
            "must not define expected sources",
        ),
    ],
)
def test_load_answer_evaluation_catalog_rejects_inconsistent_expectations(
    tmp_path: Path,
    expected_outcome: str,
    expected_sources: list[str],
    error_message: str,
) -> None:
    catalog_path = tmp_path / "answer-cases.json"
    write_catalog(
        catalog_path,
        cases=[
            make_case(
                expected_outcome=expected_outcome,
                expected_source_identifiers=expected_sources,
            )
        ],
    )

    with pytest.raises(ValueError, match=error_message):
        load_answer_evaluation_catalog(catalog_path)


def test_load_answer_evaluation_catalog_rejects_duplicate_case_ids(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "answer-cases.json"
    write_catalog(
        catalog_path,
        cases=[
            make_case(),
            make_case(),
        ],
    )

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_answer_evaluation_catalog(catalog_path)


def test_print_answer_evaluation_report_handles_conditional_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    quality = AnswerQualityEvaluation(
        expected_outcome="insufficient_evidence",
        actual_status="insufficient_evidence",
        outcome_correct=True,
        citation_correctness=None,
        abstention_correctness=True,
        passed=True,
    )
    report = AnswerEvaluationReport(
        requested_k=3,
        case_results=(
            AnswerEvaluationCaseResult(
                case_id="ANSWER-EVAL-002",
                category="insufficient_evidence",
                actual_status="insufficient_evidence",
                cited_source_identifiers=(),
                quality=quality,
                query_input_token_count=5,
                prompt_token_count=None,
                completion_token_count=None,
            ),
        ),
        outcome_accuracy=1.0,
        citation_correctness_rate=None,
        abstention_correctness_rate=1.0,
        overall_pass_rate=1.0,
        total_query_input_tokens=5,
        total_prompt_tokens=0,
        total_completion_tokens=0,
    )

    print_answer_evaluation_report(report)

    output = capsys.readouterr().out

    assert "Answer evaluation completed" in output
    assert "Outcome accuracy: 1.000" in output
    assert "Citation correctness: (not applicable)" in output
    assert "Abstention correctness: 1.000" in output
    assert "status=insufficient_evidence, passed=yes" in output
    assert "Cited: (none)" in output
