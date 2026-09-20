import math
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_BM25_K1 = 1.2
DEFAULT_BM25_B = 0.75

# Preserve meaningful incident IDs, versions, underscores, colons, dots, and hyphens.
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[._:-][a-z0-9]+)*")


@dataclass(frozen=True)
class Bm25ScoredDocument:
    """One lexical retrieval candidate and its BM25 relevance score."""

    source_identifier: str
    score: float


def tokenize_bm25(text: str) -> tuple[str, ...]:
    """Convert text into stable, case-insensitive lexical-search terms."""

    if not isinstance(text, str):
        raise TypeError("BM25 text must be a string")

    return tuple(TOKEN_PATTERN.findall(text.casefold()))


def rank_bm25_documents(
    query: str,
    documents: Mapping[str, str],
    *,
    limit: int,
    k1: float = DEFAULT_BM25_K1,
    b: float = DEFAULT_BM25_B,
) -> tuple[Bm25ScoredDocument, ...]:
    """Rank document text using the BM25 lexical relevance formula.

    BM25 rewards rare query terms and useful term repetition while avoiding
    unfair preference for unusually long documents.
    """

    query_terms = tokenize_bm25(query)

    if not query_terms:
        raise ValueError("BM25 query must contain at least one searchable term")

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("BM25 limit must be an integer")

    if limit < 1:
        raise ValueError("BM25 limit must be at least 1")

    if isinstance(k1, bool) or not isinstance(k1, int | float):
        raise TypeError("BM25 k1 must be numeric")

    if k1 <= 0:
        raise ValueError("BM25 k1 must be greater than zero")

    if isinstance(b, bool) or not isinstance(b, int | float):
        raise TypeError("BM25 b must be numeric")

    if not 0 <= b <= 1:
        raise ValueError("BM25 b must be between zero and one")

    normalized_documents = _normalize_documents(documents)

    if not normalized_documents:
        return ()

    document_term_frequencies = {
        source_identifier: Counter(tokenize_bm25(content))
        for source_identifier, content in normalized_documents.items()
    }
    document_lengths = {
        source_identifier: sum(term_frequencies.values())
        for source_identifier, term_frequencies in document_term_frequencies.items()
    }
    average_document_length = sum(document_lengths.values()) / len(document_lengths)

    if average_document_length == 0:
        return ()

    document_count = len(normalized_documents)
    scores = {source_identifier: 0.0 for source_identifier in normalized_documents}

    for term in frozenset(query_terms):
        document_frequency = sum(
            term in term_frequencies for term_frequencies in document_term_frequencies.values()
        )

        if document_frequency == 0:
            continue

        inverse_document_frequency = math.log(
            1 + ((document_count - document_frequency + 0.5) / (document_frequency + 0.5))
        )

        for source_identifier, term_frequencies in document_term_frequencies.items():
            term_frequency = term_frequencies[term]

            if term_frequency == 0:
                continue

            document_length = document_lengths[source_identifier]
            length_normalization = 1 - b + b * (document_length / average_document_length)
            denominator = term_frequency + k1 * length_normalization

            scores[source_identifier] += inverse_document_frequency * (
                term_frequency * (k1 + 1) / denominator
            )

    scored_documents = tuple(
        Bm25ScoredDocument(
            source_identifier=source_identifier,
            score=score,
        )
        for source_identifier, score in scores.items()
        if score > 0
    )

    return tuple(
        sorted(
            scored_documents,
            key=lambda document: (-document.score, document.source_identifier),
        )[:limit]
    )


def _normalize_documents(documents: Mapping[str, str]) -> dict[str, str]:
    """Validate source IDs and document content before calculating scores."""

    if not isinstance(documents, Mapping):
        raise TypeError("BM25 documents must be a mapping of source IDs to text")

    normalized_documents: dict[str, str] = {}

    for source_identifier, content in documents.items():
        if not isinstance(source_identifier, str):
            raise TypeError("BM25 document source identifiers must be strings")

        normalized_source_identifier = source_identifier.strip()

        if not normalized_source_identifier:
            raise ValueError("BM25 document source identifiers must not be empty")

        if not isinstance(content, str):
            raise TypeError("BM25 document content must be text")

        normalized_documents[normalized_source_identifier] = content

    return normalized_documents
