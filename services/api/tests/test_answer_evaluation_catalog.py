import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ANSWER_EVALUATION_PATH = REPOSITORY_ROOT / "docs" / "evaluation" / "answer-eval-cases-v1.json"
DEMO_DATA_PATH = REPOSITORY_ROOT / "docs" / "demo-data"

SUPPORTED_OUTCOMES = {
    "grounded",
    "insufficient_evidence",
}


def load_answer_evaluation_catalog() -> dict[str, object]:
    """Load the versioned executable answer-evaluation catalog."""

    return json.loads(ANSWER_EVALUATION_PATH.read_text(encoding="utf-8"))


def test_answer_evaluation_catalog_has_valid_executable_cases() -> None:
    catalog = load_answer_evaluation_catalog()

    assert catalog["suite_name"] == ("SecureCloudOps Answer Evaluation Cases")
    assert catalog["suite_version"] == "v1"
    assert catalog["default_retrieval_limit"] == 3

    cases = catalog["cases"]

    assert isinstance(cases, list)
    assert len(cases) >= 2
    assert all(isinstance(case, dict) for case in cases)

    case_ids = [case["id"] for case in cases]
    expected_outcomes = {case["expected_outcome"] for case in cases}

    assert len(case_ids) == len(set(case_ids))
    assert expected_outcomes == SUPPORTED_OUTCOMES

    for case in cases:
        assert {
            "id",
            "category",
            "tenant",
            "question",
            "expected_outcome",
            "expected_source_identifiers",
        } <= set(case)

        assert isinstance(case["id"], str)
        assert isinstance(case["category"], str)
        assert case["tenant"] == "retrieval-evaluation"
        assert isinstance(case["question"], str)
        assert case["question"].strip()
        assert case["expected_outcome"] in SUPPORTED_OUTCOMES

        expected_sources = case["expected_source_identifiers"]

        assert isinstance(expected_sources, list)

        if case["expected_outcome"] == "grounded":
            assert expected_sources
        else:
            assert expected_sources == []

        for source_identifier in expected_sources:
            assert isinstance(source_identifier, str)

            source_path, separator, chunk_index = source_identifier.partition("#chunk-")

            assert separator == "#chunk-"
            assert chunk_index.isdecimal()
            assert (DEMO_DATA_PATH / source_path).is_file()
