import json
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = (
    REPOSITORY_ROOT
    / "docs"
    / "evaluation"
    / "chunking-comparison-v0.3-controlled-corpus-50-cases.json"
)


def test_chunking_comparison_report_records_results_and_decision() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    assert report["benchmark_suite"]["case_count"] == 50
    assert report["benchmark_suite"]["document_count"] == 5

    profiles = {profile["profile_name"]: profile for profile in report["profiles"]}
    assert set(profiles) == {"current-1200-200", "smaller-600-100"}

    current = profiles["current-1200-200"]
    smaller = profiles["smaller-600-100"]

    assert current["max_chars"] == 1200
    assert current["overlap_chars"] == 200
    assert current["chunk_count"] == 7
    assert current["document_embedding_input_tokens"] == 1413
    assert current["mean_precision_at_3"] == 0.333
    assert current["mean_recall_at_3"] == 0.98

    assert smaller["max_chars"] == 600
    assert smaller["overlap_chars"] == 100
    assert smaller["chunk_count"] == 12
    assert smaller["document_embedding_input_tokens"] == 1511
    assert smaller["mean_precision_at_3"] == 0.34
    assert smaller["mean_recall_at_3"] == 0.94

    assert smaller["mean_precision_at_3"] > current["mean_precision_at_3"]
    assert current["mean_recall_at_3"] > smaller["mean_recall_at_3"]
    assert current["p95_retrieval_latency_ms"] < smaller["p95_retrieval_latency_ms"]

    deltas = report["smaller_minus_current"]
    assert deltas["precision_at_3_absolute"] == 0.007
    assert deltas["recall_at_3_absolute"] == -0.04
    assert deltas["chunk_count"] == 5
    assert deltas["document_embedding_input_tokens"] == 98
    assert deltas["precision_at_3_absolute"] == pytest.approx(
        smaller["mean_precision_at_3"] - current["mean_precision_at_3"],
        abs=0.001,
    )
    assert deltas["recall_at_3_absolute"] == pytest.approx(
        smaller["mean_recall_at_3"] - current["mean_recall_at_3"],
        abs=0.001,
    )
    assert deltas["mean_retrieval_latency_ms"] == pytest.approx(
        smaller["mean_retrieval_latency_ms"] - current["mean_retrieval_latency_ms"],
        abs=0.001,
    )
    assert deltas["p50_retrieval_latency_ms"] == pytest.approx(
        smaller["p50_retrieval_latency_ms"] - current["p50_retrieval_latency_ms"],
        abs=0.001,
    )
    assert deltas["p95_retrieval_latency_ms"] == pytest.approx(
        smaller["p95_retrieval_latency_ms"] - current["p95_retrieval_latency_ms"],
        abs=0.001,
    )
    assert deltas["chunk_count_percent"] == pytest.approx(
        ((smaller["chunk_count"] - current["chunk_count"]) / current["chunk_count"]) * 100,
        abs=0.001,
    )
    assert deltas["document_embedding_input_tokens_percent"] == pytest.approx(
        (
            (
                smaller["document_embedding_input_tokens"]
                - current["document_embedding_input_tokens"]
            )
            / current["document_embedding_input_tokens"]
        )
        * 100,
        abs=0.001,
    )

    decision = report["decision"]
    assert decision["selected_profile"] == "current-1200-200"
    assert (
        decision["production_change"]
        == "No chunking-default change is justified by this controlled benchmark."
    )
