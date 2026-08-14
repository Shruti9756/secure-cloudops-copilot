import argparse
from collections.abc import Sequence

from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.infrastructure.ollama_chat import OllamaChatClient
from app.services.rag import GroundedAnswer, answer_grounded_question
from app.services.retrieval import DEFAULT_RETRIEVAL_LIMIT, MAX_RETRIEVAL_LIMIT

DEFAULT_TENANT_SLUG = "nimbuscart"


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface for grounded local RAG answers."""
    parser = argparse.ArgumentParser(
        description=(
            "Answer a question from tenant-scoped knowledge documents using local Ollama RAG."
        )
    )
    parser.add_argument(
        "question",
        help="Incident-investigation question to answer from indexed evidence.",
    )
    parser.add_argument(
        "--tenant",
        default=DEFAULT_TENANT_SLUG,
        help=f"Tenant workspace to search (default: {DEFAULT_TENANT_SLUG}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_RETRIEVAL_LIMIT,
        help=(
            "Maximum number of evidence chunks to use "
            f"(default: {DEFAULT_RETRIEVAL_LIMIT}, maximum: {MAX_RETRIEVAL_LIMIT})."
        ),
    )

    return parser


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse and validate arguments before starting local AI work."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args.question = args.question.strip()
    args.tenant = args.tenant.strip()

    if not args.question:
        parser.error("question must not be empty")

    if not args.tenant:
        parser.error("--tenant must not be empty")

    if not 1 <= args.limit <= MAX_RETRIEVAL_LIMIT:
        parser.error(f"--limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")

    return args


def print_grounded_answer(tenant_slug: str, answer: GroundedAnswer) -> None:
    """Print the answer and source traceability without displaying raw vector data."""
    print(f"Tenant: {tenant_slug}")
    print(f"Embedding model: {answer.embedding_model}")
    print(f"Generation model: {answer.generation_model or 'not called'}")
    print()
    print("Answer")
    print(answer.answer_text)

    if answer.citation_validation is not None:
        print()
        print(
            f"Citation validation: {'passed' if answer.citation_validation.is_valid else 'failed'}"
        )

        for error in answer.citation_validation.errors:
            print(f"- {error}")

    if not answer.sources:
        return

    print()
    print("Retrieved sources")

    for source in answer.sources:
        print(
            f"- {source.source_path}#chunk-{source.chunk_index} "
            f"(cosine distance: {source.cosine_distance:.4f})"
        )

    print()
    print(
        "Usage: "
        f"query_tokens={answer.query_input_token_count}, "
        f"prompt_tokens={answer.prompt_token_count}, "
        f"completion_tokens={answer.completion_token_count}"
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run one read-only, tenant-scoped local RAG question-answering request."""
    args = parse_arguments(argv)
    session_factory = get_session_factory()

    # Both providers are local; they have no AWS, shell, or database-write permissions.
    embedding_provider = OllamaEmbeddingClient()
    chat_provider = OllamaChatClient()

    # A regular session is read-only here; no transaction commit is needed.
    with session_factory() as session:
        answer = answer_grounded_question(
            session=session,
            tenant_slug=args.tenant,
            question=args.question,
            embedding_provider=embedding_provider,
            chat_provider=chat_provider,
            limit=args.limit,
        )

    print_grounded_answer(
        tenant_slug=args.tenant,
        answer=answer,
    )


if __name__ == "__main__":
    main()
