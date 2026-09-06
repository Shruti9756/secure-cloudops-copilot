import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RETRIEVAL_EVALUATION_PATH = REPOSITORY_ROOT / "docs" / "evaluation" / "retrieval-eval-cases-v1.json"
DEMO_DATA_PATH = REPOSITORY_ROOT / "docs" / "demo-data"


def load_retrieval_evaluation_catalog() -> dict[str, object]:
    """Load the versioned synthetic retrieval benchmark."""

    return json.loads(RETRIEVAL_EVALUATION_PATH.read_text(encoding="utf-8"))


def test_retrieval_evaluation_catalog_has_valid_baseline_cases() -> None:
    """Keep the baseline benchmark reviewable and tied to real seed documents."""

    catalog = load_retrieval_evaluation_catalog()

    assert catalog["suite_name"] == "SecureCloudOps Retrieval Evaluation Cases"
    assert catalog["suite_version"] == "v1"
    assert catalog["default_retrieval_limit"] == 3

    cases = catalog["cases"]

    assert isinstance(cases, list)
    assert len(cases) >= 8
    assert all(isinstance(case, dict) for case in cases)

    case_ids = [case["id"] for case in cases]

    assert len(case_ids) == len(set(case_ids))

    for case in cases:
        assert {"id", "category", "tenant", "question", "expected_source_identifiers"} <= set(case)
        assert isinstance(case["id"], str)
        assert isinstance(case["category"], str)
        assert isinstance(case["tenant"], str)
        assert isinstance(case["question"], str)
        assert case["question"].strip()

        expected_sources = case["expected_source_identifiers"]

        assert isinstance(expected_sources, list)
        assert expected_sources

        for source_identifier in expected_sources:
            assert isinstance(source_identifier, str)

            source_path, separator, chunk_index = source_identifier.partition("#chunk-")

            assert separator == "#chunk-"
            assert chunk_index.isdecimal()
            assert (DEMO_DATA_PATH / source_path).is_file()
