import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.services.retrieval import MAX_RETRIEVAL_LIMIT
from app.services.retrieval_evaluation_runner import (
    SUPPORTED_RETRIEVAL_STRATEGIES,
    RetrievalEvaluationCase,
    RetrievalEvaluationReport,
    run_retrieval_evaluation,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG_PATH = REPOSITORY_ROOT / "docs" / "evaluation" / "retrieval-eval-cases-v1.json"
CATALOG_SUITE_NAME = "SecureCloudOps Retrieval Evaluation Cases"
CATALOG_SUITE_VERSION = "v1"


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface for a local retrieval-quality run."""

    parser = argparse.ArgumentParser(
        description=(
            "Measure local semantic retrieval quality using the versioned "
            "synthetic SecureCloudOps benchmark."
        )
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help=f"Path to the retrieval benchmark JSON (default: {DEFAULT_CATALOG_PATH}).",
    )
    parser.add_argument(
        "--strategy",
        choices=sorted(SUPPORTED_RETRIEVAL_STRATEGIES),
        default="semantic",
        help="Retrieval strategy to measure (default: semantic).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help=(
            "Number of retrieved chunks to evaluate per question. "
            "Defaults to default_retrieval_limit in the catalog."
        ),
    )

    return parser


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse and validate command-line arguments before using services."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.limit is not None and not 1 <= args.limit <= MAX_RETRIEVAL_LIMIT:
        parser.error(f"--limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")

    return args


def load_retrieval_evaluation_catalog(
    catalog_path: Path,
) -> tuple[int, tuple[RetrievalEvaluationCase, ...]]:
    """Load validated benchmark cases from a versioned JSON file."""

    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Could not read retrieval evaluation catalog: {catalog_path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Retrieval evaluation catalog is not valid JSON: {catalog_path}"
        ) from error

    if not isinstance(payload, dict):
        raise TypeError("Retrieval evaluation catalog must contain a JSON object")

    suite_name = _require_non_empty_text(payload.get("suite_name"), "suite_name")
    suite_version = _require_non_empty_text(
        payload.get("suite_version"),
        "suite_version",
    )

    if suite_name != CATALOG_SUITE_NAME:
        raise ValueError(f"Unexpected retrieval evaluation suite: {suite_name}")

    if suite_version != CATALOG_SUITE_VERSION:
        raise ValueError(f"Unsupported retrieval evaluation suite version: {suite_version}")

    default_limit = payload.get("default_retrieval_limit")

    if isinstance(default_limit, bool) or not isinstance(default_limit, int):
        raise TypeError("default_retrieval_limit must be an integer")

    if not 1 <= default_limit <= MAX_RETRIEVAL_LIMIT:
        raise ValueError(f"default_retrieval_limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")

    raw_cases = payload.get("cases")

    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Retrieval evaluation catalog must contain at least one case")

    cases = tuple(
        _parse_evaluation_case(raw_case, position=index)
        for index, raw_case in enumerate(raw_cases, start=1)
    )
    case_ids = tuple(case.case_id for case in cases)

    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Retrieval evaluation catalog case IDs must be unique")

    return default_limit, cases


def print_retrieval_evaluation_report(report: RetrievalEvaluationReport) -> None:
    """Print a concise, reviewable summary without storing evaluation results."""

    print("Retrieval evaluation completed")
    print(f"Cases evaluated: {len(report.case_results)}")
    print(f"Retrieval limit: {report.requested_k}")
    print(f"Retrieval strategy: {report.retrieval_strategy}")
    print(f"Mean Precision@{report.requested_k}: {report.mean_precision_at_k:.3f}")
    print(f"Mean Recall@{report.requested_k}: {report.mean_recall_at_k:.3f}")
    print(f"Total query input tokens: {report.total_query_input_tokens}")

    embedding_models = sorted(
        {
            result.embedding_model
            for result in report.case_results
            if result.embedding_model is not None
        }
    )
    print(f"Embedding model: {', '.join(embedding_models) if embedding_models else '(not used)'}")
    print()
    print("Per-case results:")

    for result in report.case_results:
        retrieved_sources = ", ".join(result.retrieved_source_identifiers) or "(none)"
        matched_sources = ", ".join(result.matched_source_identifiers) or "(none)"

        print(
            f"- {result.case_id}: "
            f"Precision@{report.requested_k}={result.precision_at_k:.3f}, "
            f"Recall@{report.requested_k}={result.recall_at_k:.3f}"
        )
        print(f"  Retrieved: {retrieved_sources}")
        print(f"  Matched: {matched_sources}")


def _parse_evaluation_case(
    raw_case: object,
    *,
    position: int,
) -> RetrievalEvaluationCase:
    """Convert one untrusted JSON object into a typed benchmark case."""

    if not isinstance(raw_case, dict):
        raise TypeError(f"Evaluation case {position} must be a JSON object")

    expected_source_identifiers = _require_source_identifiers(
        raw_case.get("expected_source_identifiers"),
        position=position,
    )

    return RetrievalEvaluationCase(
        case_id=_require_non_empty_text(raw_case.get("id"), f"cases[{position}].id"),
        category=_require_non_empty_text(
            raw_case.get("category"),
            f"cases[{position}].category",
        ),
        tenant_slug=_require_non_empty_text(
            raw_case.get("tenant"),
            f"cases[{position}].tenant",
        ),
        question=_require_non_empty_text(
            raw_case.get("question"),
            f"cases[{position}].question",
        ),
        expected_source_identifiers=expected_source_identifiers,
    )


def _require_non_empty_text(value: object, field_name: str) -> str:
    """Return one trimmed JSON string or raise a helpful catalog error."""

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    normalized_value = value.strip()

    if not normalized_value:
        raise ValueError(f"{field_name} must not be empty")

    return normalized_value


def _require_source_identifiers(
    value: object,
    *,
    position: int,
) -> tuple[str, ...]:
    """Validate expected document-and-chunk IDs for one benchmark case."""

    if not isinstance(value, list) or not value:
        raise ValueError(f"cases[{position}].expected_source_identifiers must be a non-empty list")

    source_identifiers = tuple(
        _require_non_empty_text(
            source_identifier,
            f"cases[{position}].expected_source_identifiers",
        )
        for source_identifier in value
    )

    if len(source_identifiers) != len(set(source_identifiers)):
        raise ValueError(
            f"cases[{position}].expected_source_identifiers must not contain duplicates"
        )

    for source_identifier in source_identifiers:
        source_path, separator, chunk_index = source_identifier.partition("#chunk-")

        if not source_path or separator != "#chunk-" or not chunk_index.isdecimal():
            raise ValueError(
                "Expected source identifiers must use source-path#chunk-numeric-index format"
            )

    return source_identifiers


def main(argv: Sequence[str] | None = None) -> None:
    """Run the local benchmark against real Ollama embeddings and PostgreSQL."""

    args = parse_arguments(argv)
    catalog_limit, cases = load_retrieval_evaluation_catalog(args.catalog)
    limit = args.limit if args.limit is not None else catalog_limit

    embedding_provider = OllamaEmbeddingClient()
    session_factory = get_session_factory()

    # Evaluation is read-only: it creates no documents, embeddings, or audit data.
    with session_factory() as session:
        report = run_retrieval_evaluation(
            session=session,
            cases=cases,
            embedding_provider=embedding_provider,
            limit=limit,
            strategy=args.strategy,
        )

    print_retrieval_evaluation_report(report)


if __name__ == "__main__":
    main()
