import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from app.services.retrieval_evaluation_runner import RetrievalEvaluationCase

CHUNKING_LABEL_SUITE_NAME = "SecureCloudOps Chunking Evaluation Labels"
CHUNKING_LABEL_SUITE_VERSION = "v1"


@dataclass(frozen=True)
class ChunkingCaseLabels:
    case_id: str
    expected_source_identifiers: tuple[str, ...]


@dataclass(frozen=True)
class ChunkingLabelCatalog:
    base_catalog: str
    profile_name: str
    max_chars: int
    overlap_chars: int
    case_labels: tuple[ChunkingCaseLabels, ...]


def load_chunking_label_catalog(
    catalog_path: Path,
) -> ChunkingLabelCatalog:
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Could not read chunking label catalogue: {catalog_path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Chunking label catalogue is not valid JSON: {catalog_path}") from error

    if not isinstance(payload, dict):
        raise TypeError("Chunking label catalogue must contain a JSON object")

    suite_name = _require_non_empty_text(
        payload.get("suite_name"),
        "suite_name",
    )
    suite_version = _require_non_empty_text(
        payload.get("suite_version"),
        "suite_version",
    )

    if suite_name != CHUNKING_LABEL_SUITE_NAME:
        raise ValueError(f"Unexpected chunking label suite: {suite_name}")

    if suite_version != CHUNKING_LABEL_SUITE_VERSION:
        raise ValueError(f"Unsupported chunking label suite version: {suite_version}")

    base_catalog = _require_non_empty_text(
        payload.get("base_catalog"),
        "base_catalog",
    )
    profile_name = _require_non_empty_text(
        payload.get("profile_name"),
        "profile_name",
    )
    max_chars = _require_integer(
        payload.get("max_chars"),
        "max_chars",
    )
    overlap_chars = _require_integer(
        payload.get("overlap_chars"),
        "overlap_chars",
    )

    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")

    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be zero or greater and less than max_chars")

    raw_cases = payload.get("cases")

    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Chunking label catalogue must contain at least one case")

    case_labels = tuple(
        _parse_case_labels(raw_case, position=index)
        for index, raw_case in enumerate(raw_cases, start=1)
    )
    case_ids = tuple(case.case_id for case in case_labels)

    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Chunking label catalogue case IDs must be unique")

    return ChunkingLabelCatalog(
        base_catalog=base_catalog,
        profile_name=profile_name,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
        case_labels=case_labels,
    )


def apply_chunking_labels(
    cases: Sequence[RetrievalEvaluationCase],
    catalog: ChunkingLabelCatalog,
    *,
    tenant_slug: str,
) -> tuple[RetrievalEvaluationCase, ...]:
    normalized_tenant_slug = tenant_slug.strip()

    if not normalized_tenant_slug:
        raise ValueError("Temporary tenant slug must not be empty")

    labels_by_case_id = {labels.case_id: labels for labels in catalog.case_labels}
    base_case_ids = {case.case_id for case in cases}
    label_case_ids = set(labels_by_case_id)

    if label_case_ids != base_case_ids:
        missing_case_ids = sorted(base_case_ids - label_case_ids)
        unknown_case_ids = sorted(label_case_ids - base_case_ids)
        raise ValueError(
            "Chunking label case IDs do not match the base cases: "
            f"missing={missing_case_ids}, "
            f"unknown={unknown_case_ids}"
        )

    return tuple(
        replace(
            case,
            tenant_slug=normalized_tenant_slug,
            expected_source_identifiers=(
                labels_by_case_id[case.case_id].expected_source_identifiers
            ),
        )
        for case in cases
    )


def _parse_case_labels(
    raw_case: object,
    *,
    position: int,
) -> ChunkingCaseLabels:
    if not isinstance(raw_case, dict):
        raise TypeError(f"Chunking label case {position} must be a JSON object")

    if set(raw_case) != {
        "id",
        "expected_source_identifiers",
    }:
        raise ValueError(f"Chunking label case {position} has unexpected fields")

    case_id = _require_non_empty_text(
        raw_case.get("id"),
        f"cases[{position}].id",
    )
    raw_sources = raw_case.get("expected_source_identifiers")

    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError(f"cases[{position}].expected_source_identifiers must be a non-empty list")

    source_identifiers = tuple(
        _require_source_identifier(
            source_identifier,
            position=position,
        )
        for source_identifier in raw_sources
    )

    if len(source_identifiers) != len(set(source_identifiers)):
        raise ValueError(
            f"cases[{position}].expected_source_identifiers must not contain duplicates"
        )

    return ChunkingCaseLabels(
        case_id=case_id,
        expected_source_identifiers=source_identifiers,
    )


def _require_source_identifier(
    value: object,
    *,
    position: int,
) -> str:
    source_identifier = _require_non_empty_text(
        value,
        f"cases[{position}].expected_source_identifiers",
    )
    source_path, separator, chunk_index = source_identifier.partition("#chunk-")

    if not source_path or separator != "#chunk-" or not chunk_index.isdecimal():
        raise ValueError(
            "Expected source identifiers must use source-path#chunk-numeric-index format"
        )

    return source_identifier


def _require_non_empty_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    normalized_value = value.strip()

    if not normalized_value:
        raise ValueError(f"{field_name} must not be empty")

    return normalized_value


def _require_integer(
    value: object,
    field_name: str,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")

    return value
