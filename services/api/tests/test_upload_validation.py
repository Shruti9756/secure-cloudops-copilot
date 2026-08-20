import pytest

from app.services.upload_validation import (
    MAX_TEXT_UPLOAD_BYTES,
    validate_and_decode_text_upload,
)


def test_validate_and_decode_text_upload_normalizes_an_allowed_markdown_file() -> None:
    result = validate_and_decode_text_upload(
        filename="Checkout Latency Runbook.MD",
        content_bytes=b"# Checkout Latency Runbook\n\nInspect Redis metrics first.",
    )

    assert result.original_filename == "Checkout Latency Runbook.MD"
    assert result.source_path == "uploads/checkout-latency-runbook.md"
    assert result.content_type == "text/markdown"
    assert result.content == "# Checkout Latency Runbook\n\nInspect Redis metrics first."


@pytest.mark.parametrize(
    ("filename", "expected_error"),
    [
        ("../private.md", "must not include a path"),
        ("runbooks\\private.md", "must not include a path"),
        ("deployment-record.pdf", "Only .md and .txt"),
        ("   ", "must include a filename"),
    ],
)
def test_validate_and_decode_text_upload_rejects_unsafe_or_unsupported_filenames(
    filename: str,
    expected_error: str,
) -> None:
    with pytest.raises(ValueError, match=expected_error):
        validate_and_decode_text_upload(
            filename=filename,
            content_bytes=b"# Safe content",
        )


def test_validate_and_decode_text_upload_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        validate_and_decode_text_upload(
            filename="runbook.md",
            content_bytes=b"",
        )


def test_validate_and_decode_text_upload_rejects_whitespace_only_content() -> None:
    with pytest.raises(ValueError, match="only whitespace"):
        validate_and_decode_text_upload(
            filename="runbook.md",
            content_bytes=b" \n\t ",
        )


def test_validate_and_decode_text_upload_rejects_non_utf8_content() -> None:
    with pytest.raises(ValueError, match="valid UTF-8 text"):
        validate_and_decode_text_upload(
            filename="runbook.txt",
            content_bytes=b"\xff\xfe",
        )


def test_validate_and_decode_text_upload_rejects_oversized_content() -> None:
    with pytest.raises(ValueError, match="text-upload limit"):
        validate_and_decode_text_upload(
            filename="runbook.txt",
            content_bytes=b"x" * (MAX_TEXT_UPLOAD_BYTES + 1),
        )


def test_validate_and_decode_text_upload_assigns_plain_text_content_type() -> None:
    result = validate_and_decode_text_upload(
        filename="Checkout Notes.txt",
        content_bytes=b"Inspect Redis eviction metrics.",
    )

    assert result.source_path == "uploads/checkout-notes.txt"
    assert result.content_type == "text/plain"
