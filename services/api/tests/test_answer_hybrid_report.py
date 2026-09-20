import json
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVALUATION_DIRECTORY = REPOSITORY_ROOT / "docs" / "evaluation"

SEMANTIC_BASELINE_PATH = EVALUATION_DIRECTORY / "answer-baseline-v0.3-controlled-corpus.json"
HYBRID_REPORT_PATH = EVALUATION_DIRECTORY / "answer-hybrid-v0.3-controlled-corpus.json"


def load_report(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_hybrid_answer_report_records_quality_and_tradeoffs() -> None:
    baseline = load_report(SEMANTIC_BASELINE_PATH)
    hybrid = load_report(HYBRID_REPORT_PATH)

    assert hybrid["benchmark_suite"]["case_count"] == 8

    configuration = hybrid["configuration"]
    assert configuration["retrieval_strategy"] == (
        "hybrid semantic and BM25 retrieval with reciprocal rank fusion"
    )
    assert configuration["retrieval_limit"] == 3
    assert configuration["hybrid_candidate_multiplier"] == 3

    metrics = hybrid["aggregate_metrics"]
    assert metrics["outcome_accuracy"] == 1.0
    assert metrics["citation_correctness_rate"] == 1.0
    assert metrics["abstention_correctness_rate"] == 1.0
    assert metrics["overall_pass_rate"] == 1.0

    case_results = hybrid["case_results"]
    assert len(case_results) == 8
    assert all(case["passed"] is True for case in case_results)

    grounded_cases = [case for case in case_results if case["actual_status"] == "grounded"]
    abstention_cases = [
        case for case in case_results if case["actual_status"] == "insufficient_evidence"
    ]

    assert len(grounded_cases) == 4
    assert len(abstention_cases) == 4
    assert all(case["citation_correctness"] is True for case in grounded_cases)
    assert all(case["cited_source_identifiers"] for case in grounded_cases)
    assert all(case["abstention_correctness"] is True for case in abstention_cases)
    assert all(not case["cited_source_identifiers"] for case in abstention_cases)

    baseline_metrics = baseline["aggregate_metrics"]
    comparison = hybrid["comparison_with_semantic_baseline"]
    quality_deltas = comparison["quality_metric_deltas"]
    token_deltas = comparison["token_count_deltas"]

    for metric_name in (
        "outcome_accuracy",
        "citation_correctness_rate",
        "abstention_correctness_rate",
        "overall_pass_rate",
    ):
        assert quality_deltas[metric_name] == (metrics[metric_name] - baseline_metrics[metric_name])

    assert token_deltas["total_query_input_tokens"] == (
        metrics["total_query_input_tokens"] - baseline_metrics["total_query_input_tokens"]
    )
    assert token_deltas["total_prompt_tokens"] == (
        metrics["total_prompt_tokens"] - baseline_metrics["total_prompt_tokens"]
    )
    assert token_deltas["total_completion_tokens"] == (
        metrics["total_completion_tokens"] - baseline_metrics["total_completion_tokens"]
    )

    retrieval_evidence = hybrid["retrieval_improvement_evidence"]
    assert retrieval_evidence["absolute_recall_at_3_improvement"] == pytest.approx(
        retrieval_evidence["hybrid_mean_recall_at_3"]
        - retrieval_evidence["semantic_mean_recall_at_3"],
        abs=0.001,
    )
