import json
from pathlib import Path

import pytest

from app.services.chunking_evaluation_catalog import (
    apply_chunking_labels,
    load_chunking_label_catalog,
)
from scripts.evaluate_retrieval import (
    load_retrieval_evaluation_catalog,
)
from scripts.inspect_chunking_profiles import build_chunking_snapshot

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BASE_CATALOG_PATH = REPOSITORY_ROOT / "docs" / "evaluation" / "retrieval-eval-cases-v1.json"
CHUNKING_LABELS_PATH = REPOSITORY_ROOT / "docs" / "evaluation" / "chunking-eval-labels-v1.json"
DEMO_DATA_PATH = REPOSITORY_ROOT / "docs" / "demo-data"


def load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert isinstance(payload, dict)

    return payload


def test_smaller_chunking_labels_cover_every_base_case() -> None:
    base_catalog = load_json_object(BASE_CATALOG_PATH)
    label_catalog = load_json_object(CHUNKING_LABELS_PATH)

    assert label_catalog["suite_name"] == ("SecureCloudOps Chunking Evaluation Labels")
    assert label_catalog["suite_version"] == "v1"
    assert label_catalog["base_catalog"] == ("docs/evaluation/retrieval-eval-cases-v1.json")
    assert label_catalog["profile_name"] == "smaller-600-100"
    assert label_catalog["max_chars"] == 600
    assert label_catalog["overlap_chars"] == 100

    base_cases = base_catalog["cases"]
    label_cases = label_catalog["cases"]

    assert isinstance(base_cases, list)
    assert isinstance(label_cases, list)
    assert len(base_cases) == 50
    assert len(label_cases) == 50

    base_case_ids = [case["id"] for case in base_cases]
    label_case_ids = [case["id"] for case in label_cases]

    assert len(base_case_ids) == len(set(base_case_ids))
    assert len(label_case_ids) == len(set(label_case_ids))
    assert set(label_case_ids) == set(base_case_ids)


def test_smaller_chunking_labels_reference_real_profile_chunks() -> None:
    label_catalog = load_json_object(CHUNKING_LABELS_PATH)
    snapshot = build_chunking_snapshot(DEMO_DATA_PATH)

    documents = snapshot["documents"]

    assert isinstance(documents, list)

    available_source_identifiers: set[str] = set()

    for document in documents:
        source_path = document["source_path"]
        profiles = document["profiles"]

        assert isinstance(source_path, str)
        assert isinstance(profiles, list)

        smaller_profile = next(
            profile for profile in profiles if profile["profile_name"] == "smaller-600-100"
        )

        for chunk in smaller_profile["chunks"]:
            available_source_identifiers.add(f"{source_path}#chunk-{chunk['chunk_index']}")

    assert len(available_source_identifiers) == 12

    label_cases = label_catalog["cases"]

    assert isinstance(label_cases, list)

    for case in label_cases:
        assert set(case) == {
            "id",
            "expected_source_identifiers",
        }

        expected_sources = case["expected_source_identifiers"]

        assert isinstance(case["id"], str)
        assert isinstance(expected_sources, list)
        assert expected_sources
        assert len(expected_sources) == len(set(expected_sources))

        for source_identifier in expected_sources:
            assert isinstance(source_identifier, str)
            assert source_identifier in available_source_identifiers


def test_runtime_loader_reads_the_reviewed_label_catalog() -> None:
    catalog = load_chunking_label_catalog(CHUNKING_LABELS_PATH)

    assert catalog.base_catalog == ("docs/evaluation/retrieval-eval-cases-v1.json")
    assert catalog.profile_name == "smaller-600-100"
    assert catalog.max_chars == 600
    assert catalog.overlap_chars == 100
    assert len(catalog.case_labels) == 50


def test_apply_chunking_labels_rewrites_tenant_and_sources() -> None:
    _, base_cases = load_retrieval_evaluation_catalog(BASE_CATALOG_PATH)
    label_catalog = load_chunking_label_catalog(CHUNKING_LABELS_PATH)

    evaluation_cases = apply_chunking_labels(
        base_cases,
        label_catalog,
        tenant_slug="temporary-smaller-profile",
    )

    assert len(evaluation_cases) == 50
    assert all(case.tenant_slug == "temporary-smaller-profile" for case in evaluation_cases)
    assert evaluation_cases[0].expected_source_identifiers == (
        "deployments/checkout-2.4.0.md#chunk-1",
        "runbooks/checkout-latency.md#chunk-1",
    )


def test_apply_chunking_labels_rejects_missing_cases() -> None:
    _, base_cases = load_retrieval_evaluation_catalog(BASE_CATALOG_PATH)
    label_catalog = load_chunking_label_catalog(CHUNKING_LABELS_PATH)

    with pytest.raises(
        ValueError,
        match="do not match the base cases",
    ):
        apply_chunking_labels(
            base_cases[:-1],
            label_catalog,
            tenant_slug="temporary-smaller-profile",
        )
