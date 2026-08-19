"""Deterministic redaction of common credential-like values before AI ingestion."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RedactionResult:
    """Safe content plus transparent, non-secret metadata about replacements."""

    content: str
    redaction_count: int
    redaction_types: tuple[str, ...]


@dataclass(frozen=True)
class SecretRedactionRule:
    """One narrowly scoped pattern that should never enter the knowledge base."""

    label: str
    pattern: re.Pattern[str]


SECRET_REDACTION_RULES = (
    SecretRedactionRule(
        label="AWS_ACCESS_KEY_ID",
        # AWS access-key IDs use a known prefix and exactly 16 following characters.
        pattern=re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ),
    SecretRedactionRule(
        label="AWS_SECRET_ACCESS_KEY",
        # Require an explicit variable name so ordinary prose is not redacted accidentally.
        pattern=re.compile(
            r"(?P<prefix>\bAWS_SECRET_ACCESS_KEY\s*[:=]\s*)[^\s]+",
            re.IGNORECASE,
        ),
    ),
    SecretRedactionRule(
        label="BEARER_TOKEN",
        # Only redact a token when it follows the standard Authorization header shape.
        pattern=re.compile(
            r"(?P<prefix>\bAuthorization\s*:\s*Bearer\s+)[A-Za-z0-9._~+/=-]+",
            re.IGNORECASE,
        ),
    ),
)


def redact_secrets(content: str) -> RedactionResult:
    """Replace recognized secrets before text is stored, embedded, or retrieved."""
    if not isinstance(content, str):
        raise TypeError("Content must be a string")

    redacted_content = content
    redaction_count = 0
    redaction_types: list[str] = []

    for rule in SECRET_REDACTION_RULES:
        redacted_content, replacement_count = rule.pattern.subn(
            lambda match, label=rule.label: _replacement_for_match(match, label),
            redacted_content,
        )

        if replacement_count:
            redaction_count += replacement_count
            redaction_types.extend([rule.label] * replacement_count)

    # dict preserves insertion order, so the metadata is stable and easy to test.
    unique_redaction_types = tuple(dict.fromkeys(redaction_types))

    return RedactionResult(
        content=redacted_content,
        redaction_count=redaction_count,
        redaction_types=unique_redaction_types,
    )


def _replacement_for_match(match: re.Match[str], label: str) -> str:
    """Keep a safe key/header prefix while replacing only its sensitive value."""
    prefix = match.groupdict().get("prefix", "")
    return f"{prefix}[REDACTED: {label}]"
