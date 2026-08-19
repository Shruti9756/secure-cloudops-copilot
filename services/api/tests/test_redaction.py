import pytest

from app.services.redaction import redact_secrets


def test_redact_secrets_replaces_common_credential_shapes() -> None:
    content = (
        "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF\n"
        "AWS_SECRET_ACCESS_KEY=example-secret-value\n"
        "Authorization: Bearer example-token-123"
    )

    result = redact_secrets(content)

    assert result.content == (
        "AWS_ACCESS_KEY_ID=[REDACTED: AWS_ACCESS_KEY_ID]\n"
        "AWS_SECRET_ACCESS_KEY=[REDACTED: AWS_SECRET_ACCESS_KEY]\n"
        "Authorization: Bearer [REDACTED: BEARER_TOKEN]"
    )
    assert result.redaction_count == 3
    assert result.redaction_types == (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "BEARER_TOKEN",
    )


def test_redact_secrets_preserves_ordinary_document_content() -> None:
    content = "# Checkout Runbook\n\nInspect Redis eviction metrics before making changes."

    result = redact_secrets(content)

    assert result.content == content
    assert result.redaction_count == 0
    assert result.redaction_types == ()


def test_redact_secrets_is_idempotent() -> None:
    """Running ingestion again must not repeatedly alter already-safe content."""
    content = "Authorization: Bearer example-token-123"

    once = redact_secrets(content)
    twice = redact_secrets(once.content)

    assert twice.content == once.content
    assert twice.redaction_count == 0
    assert twice.redaction_types == ()


def test_redact_secrets_rejects_non_string_content() -> None:
    with pytest.raises(TypeError, match="Content must be a string"):
        redact_secrets(123)  # type: ignore[arg-type]
