"""Deterministic redaction of credentials and narrow PII before AI ingestion."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RedactionResult:
    """Safe content plus transparent, non-sensitive replacement metadata."""

    content: str
    redaction_count: int
    redaction_types: tuple[str, ...]


@dataclass(frozen=True)
class SensitiveDataRedactionRule:
    """One narrow sensitive-data pattern that must not enter the knowledge base."""

    label: str
    pattern: re.Pattern[str]


SENSITIVE_DATA_REDACTION_RULES = (
    SensitiveDataRedactionRule(
        label="AWS_ACCESS_KEY_ID",
        # AWS access-key IDs use a known prefix and exactly 16 following characters.
        pattern=re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ),
    SensitiveDataRedactionRule(
        label="AWS_SECRET_ACCESS_KEY",
        # Require an explicit variable name so ordinary prose is not redacted accidentally.
        pattern=re.compile(
            r"(?P<prefix>\bAWS_SECRET_ACCESS_KEY\s*[:=]\s*)[^\s]+",
            re.IGNORECASE,
        ),
    ),
    SensitiveDataRedactionRule(
        label="BEARER_TOKEN",
        # Only redact a token when it follows the standard Authorization header shape.
        pattern=re.compile(
            r"(?P<prefix>\bAuthorization\s*:\s*Bearer\s+)[A-Za-z0-9._~+/=-]+",
            re.IGNORECASE,
        ),
    ),
    SensitiveDataRedactionRule(
        label="EMAIL_ADDRESS",
        # A standard email shape is specific enough for deterministic redaction.
        pattern=re.compile(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}\b",
            re.IGNORECASE,
        ),
    ),
    SensitiveDataRedactionRule(
        label="PHONE_NUMBER",
        # Require an explicit label to avoid mistaking ordinary metric values for phones.
        pattern=re.compile(
            r"(?P<prefix>\b(?:phone|mobile|telephone|contact\s+number)\s*[:=]\s*)"
            r"\+?[0-9][0-9(). -]{5,}[0-9]\b",
            re.IGNORECASE,
        ),
    ),
)


def redact_sensitive_content(content: str) -> RedactionResult:
    """Redact recognized secrets and narrow PII before AI processing."""

    if not isinstance(content, str):
        raise TypeError("Content must be a string")

    redacted_content = content
    redaction_count = 0
    redaction_types: list[str] = []

    for rule in SENSITIVE_DATA_REDACTION_RULES:
        redacted_content, replacement_count = rule.pattern.subn(
            lambda match, label=rule.label: _replacement_for_match(match, label),
            redacted_content,
        )

        if replacement_count:
            redaction_count += replacement_count
            redaction_types.extend([rule.label] * replacement_count)

    unique_redaction_types = tuple(dict.fromkeys(redaction_types))

    return RedactionResult(
        content=redacted_content,
        redaction_count=redaction_count,
        redaction_types=unique_redaction_types,
    )


def _replacement_for_match(match: re.Match[str], label: str) -> str:
    """Keep a safe field prefix while replacing only its sensitive value."""

    prefix = match.groupdict().get("prefix", "")
    return f"{prefix}[REDACTED: {label}]"
