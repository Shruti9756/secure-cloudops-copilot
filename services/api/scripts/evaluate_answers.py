import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.infrastructure.ollama_chat import OllamaChatClient
from app.services.answer_evaluation import (
    SUPPORTED_EXPECTED_OUTCOMES,
    ExpectedAnswerOutcome,
)
from app.services.answer_evaluation_runner import (
    AnswerEvaluationCase,
    AnswerEvaluationReport,
    run_answer_evaluation,
)
from app.services.retrieval import MAX_RETRIEVAL_LIMIT

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG_PATH = REPOSITORY_ROOT / "docs" / "evaluation" / "answer-eval-cases-v1.json"
CATALOG_SUITE_NAME = "SecureCloudOps Answer Evaluation Cases"
CATALOG_SUITE_VERSION = "v1"


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface for an answer-quality run."""

    parser = argparse.ArgumentParser(
        description=(
            "Measure grounded-answer, citation, and safe-abstention quality "
            "using the versioned SecureCloudOps benchmark."
        )
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help=f"Path to the answer benchmark JSON (default: {DEFAULT_CATALOG_PATH}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help=(
            "Number of chunks retrieved per question. "
            "Defaults to default_retrieval_limit in the catalog."
        ),
    )
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help=(
            "Run only one evaluation case ID. Repeat this option to run multiple selected cases."
        ),
    )

    return parser


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse and validate command-line arguments."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.limit is not None and not 1 <= args.limit <= MAX_RETRIEVAL_LIMIT:
        parser.error(f"--limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")

    return args


def load_answer_evaluation_catalog(
    catalog_path: Path,
) -> tuple[int, tuple[AnswerEvaluationCase, ...]]:
    """Load validated answer-evaluation cases from versioned JSON."""

    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Could not read answer evaluation catalog: {catalog_path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Answer evaluation catalog is not valid JSON: {catalog_path}") from error

    if not isinstance(payload, dict):
        raise TypeError("Answer evaluation catalog must contain a JSON object")

    suite_name = _require_non_empty_text(payload.get("suite_name"), "suite_name")
    suite_version = _require_non_empty_text(
        payload.get("suite_version"),
        "suite_version",
    )

    if suite_name != CATALOG_SUITE_NAME:
        raise ValueError(f"Unexpected answer evaluation suite: {suite_name}")

    if suite_version != CATALOG_SUITE_VERSION:
        raise ValueError(f"Unsupported answer evaluation suite version: {suite_version}")

    default_limit = payload.get("default_retrieval_limit")

    if isinstance(default_limit, bool) or not isinstance(default_limit, int):
        raise TypeError("default_retrieval_limit must be an integer")

    if not 1 <= default_limit <= MAX_RETRIEVAL_LIMIT:
        raise ValueError(f"default_retrieval_limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")

    raw_cases = payload.get("cases")

    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Answer evaluation catalog must contain at least one case")

    cases = tuple(
        _parse_evaluation_case(raw_case, position=index)
        for index, raw_case in enumerate(raw_cases, start=1)
    )
    case_ids = tuple(case.case_id for case in cases)

    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Answer evaluation catalog case IDs must be unique")

    return default_limit, cases


def select_answer_evaluation_cases(
    cases: Sequence[AnswerEvaluationCase],
    requested_case_ids: Sequence[str] | None,
) -> tuple[AnswerEvaluationCase, ...]:
    """Select requested cases while rejecting unknown or duplicate IDs."""

    if not requested_case_ids:
        return tuple(cases)

    normalized_case_ids = tuple(case_id.strip() for case_id in requested_case_ids)

    if any(not case_id for case_id in normalized_case_ids):
        raise ValueError("Requested answer-evaluation case IDs must not be empty")

    if len(normalized_case_ids) != len(set(normalized_case_ids)):
        raise ValueError("Requested answer-evaluation case IDs must not contain duplicates")

    cases_by_id = {case.case_id: case for case in cases}
    unknown_case_ids = tuple(
        case_id for case_id in normalized_case_ids if case_id not in cases_by_id
    )

    if unknown_case_ids:
        raise ValueError(f"Unknown answer-evaluation case ID(s): {', '.join(unknown_case_ids)}")

    return tuple(cases_by_id[case_id] for case_id in normalized_case_ids)


def print_answer_evaluation_report(report: AnswerEvaluationReport) -> None:
    """Print a reviewable answer-quality report."""

    print("Answer evaluation completed")
    print(f"Cases evaluated: {len(report.case_results)}")
    print(f"Retrieval limit: {report.requested_k}")
    print(f"Outcome accuracy: {report.outcome_accuracy:.3f}")
    print(f"Citation correctness: {_format_optional_rate(report.citation_correctness_rate)}")
    print(f"Abstention correctness: {_format_optional_rate(report.abstention_correctness_rate)}")
    print(f"Overall pass rate: {report.overall_pass_rate:.3f}")
    print(f"Total query input tokens: {report.total_query_input_tokens}")
    print(f"Total prompt tokens: {report.total_prompt_tokens}")
    print(f"Total completion tokens: {report.total_completion_tokens}")
    print()
    print("Per-case results:")

    for result in report.case_results:
        cited_sources = ", ".join(result.cited_source_identifiers) or "(none)"

        print(
            f"- {result.case_id} ({result.category}): "
            f"status={result.actual_status}, "
            f"passed={'yes' if result.quality.passed else 'no'}"
        )
        print(
            "  Citation correctness: "
            f"{_format_optional_boolean(result.quality.citation_correctness)}"
        )
        print(
            "  Abstention correctness: "
            f"{_format_optional_boolean(result.quality.abstention_correctness)}"
        )
        print(f"  Cited: {cited_sources}")


def _parse_evaluation_case(
    raw_case: object,
    *,
    position: int,
) -> AnswerEvaluationCase:
    """Convert one untrusted JSON object into a typed evaluation case."""

    if not isinstance(raw_case, dict):
        raise TypeError(f"Evaluation case {position} must be a JSON object")

    expected_outcome_text = _require_non_empty_text(
        raw_case.get("expected_outcome"),
        f"cases[{position}].expected_outcome",
    )

    if expected_outcome_text not in SUPPORTED_EXPECTED_OUTCOMES:
        raise ValueError(
            f"cases[{position}].expected_outcome must be grounded or insufficient_evidence"
        )

    expected_outcome = cast(ExpectedAnswerOutcome, expected_outcome_text)
    expected_source_identifiers = _require_source_identifiers(
        raw_case.get("expected_source_identifiers"),
        position=position,
    )

    if expected_outcome == "grounded" and not expected_source_identifiers:
        raise ValueError(f"Grounded case {position} must define expected source identifiers")

    if expected_outcome == "insufficient_evidence" and expected_source_identifiers:
        raise ValueError(f"Insufficient-evidence case {position} must not define expected sources")

    return AnswerEvaluationCase(
        case_id=_require_non_empty_text(
            raw_case.get("id"),
            f"cases[{position}].id",
        ),
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
        expected_outcome=expected_outcome,
        expected_source_identifiers=expected_source_identifiers,
    )


def _require_non_empty_text(value: object, field_name: str) -> str:
    """Return one trimmed string or raise a helpful catalog error."""

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
    """Validate expected source identifiers, including an allowed empty list."""

    if not isinstance(value, list):
        raise TypeError(f"cases[{position}].expected_source_identifiers must be a list")

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


def _format_optional_rate(value: float | None) -> str:
    """Format conditional rates that might not apply to a run."""

    return "(not applicable)" if value is None else f"{value:.3f}"


def _format_optional_boolean(value: bool | None) -> str:
    """Format conditional per-case measurements."""

    if value is None:
        return "(not applicable)"

    return "passed" if value else "failed"


def main(argv: Sequence[str] | None = None) -> None:
    """Run the benchmark against real PostgreSQL retrieval and Ollama generation."""

    args = parse_arguments(argv)
    catalog_limit, cases = load_answer_evaluation_catalog(args.catalog)
    selected_cases = select_answer_evaluation_cases(cases, args.case_ids)
    limit = args.limit if args.limit is not None else catalog_limit

    embedding_provider = OllamaEmbeddingClient()
    chat_provider = OllamaChatClient()
    session_factory = get_session_factory()

    with session_factory() as session:
        report = run_answer_evaluation(
            session=session,
            cases=selected_cases,
            embedding_provider=embedding_provider,
            chat_provider=chat_provider,
            limit=limit,
        )

    print_answer_evaluation_report(report)


if __name__ == "__main__":
    main()
