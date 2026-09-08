import json
from pathlib import Path

import pytest

from scripts.evaluate_retrieval import (
    DEFAULT_CATALOG_PATH,
    load_retrieval_evaluation_catalog,
    parse_arguments,
)


def write_catalog(
    catalog_path: Path,
    *,
    cases: list[dict[str, object]],
    default_limit: int = 3,
) -> None:
    """Write a minimal synthetic benchmark file for parser tests."""

    catalog_path.write_text(
        json.dumps(
            {
                "suite_name": "SecureCloudOps Retrieval Evaluation Cases",
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
    assert args.strategy == "semantic"


def test_parse_arguments_accepts_a_catalog_path_and_retrieval_limit() -> None:
    args = parse_arguments(
        (
            "--catalog",
            "custom-cases.json",
            "--limit",
            "2",
            "--strategy",
            "hybrid",
        )
    )

    assert args.catalog == Path("custom-cases.json")
    assert args.limit == 2
    assert args.strategy == "hybrid"


def test_parse_arguments_rejects_an_unsupported_strategy() -> None:
    with pytest.raises(SystemExit):
        parse_arguments(("--strategy", "unsupported"))


@pytest.mark.parametrize("limit", ("0", "11"))
def test_parse_arguments_rejects_an_out_of_range_limit(limit: str) -> None:
    with pytest.raises(SystemExit):
        parse_arguments(("--limit", limit))


def test_load_retrieval_evaluation_catalog_returns_typed_cases(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "retrieval-cases.json"
    write_catalog(
        catalog_path,
        cases=[
            {
                "id": "RET-EVAL-001",
                "category": "deployment",
                "tenant": "nimbuscart",
                "question": "What changed in checkout version 2.4.0?",
                "expected_source_identifiers": ["deployments/checkout-2.4.0.md#chunk-0"],
            }
        ],
    )

    default_limit, cases = load_retrieval_evaluation_catalog(catalog_path)

    assert default_limit == 3
    assert len(cases) == 1
    assert cases[0].case_id == "RET-EVAL-001"
    assert cases[0].tenant_slug == "nimbuscart"
    assert cases[0].expected_source_identifiers == ("deployments/checkout-2.4.0.md#chunk-0",)


def test_load_retrieval_evaluation_catalog_rejects_an_empty_case_list(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "retrieval-cases.json"
    write_catalog(catalog_path, cases=[])

    with pytest.raises(ValueError, match="must contain at least one case"):
        load_retrieval_evaluation_catalog(catalog_path)
