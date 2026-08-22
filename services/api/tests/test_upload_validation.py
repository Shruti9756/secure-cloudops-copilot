"""Tests for upload filename, size, and extraction validation."""

from io import BytesIO

import pymupdf
import pytest
from docx import Document

from app.services.upload_validation import (
    MAX_DOCUMENT_UPLOAD_BYTES,
    validate_and_extract_upload,
)


def make_pdf_bytes() -> bytes:
    """Build a small digital PDF accepted by the safe extraction path."""
    pdf_document = pymupdf.open()

    try:
        page = pdf_document.new_page()
        page.insert_text((72, 72), "PDF Redis Investigation")
        return pdf_document.tobytes()
    finally:
        pdf_document.close()


def make_docx_bytes() -> bytes:
    """Build a small DOCX accepted by the safe extraction path."""
    document = Document()
    document.add_heading("DOCX Redis Investigation", level=1)

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def test_validate_and_extract_upload_normalizes_an_allowed_markdown_file() -> None:
    result = validate_and_extract_upload(
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
        ("deployment-record.exe", "Only .md, .txt, .pdf, and .docx"),
        ("   ", "must include a filename"),
    ],
)
def test_validate_and_extract_upload_rejects_unsafe_or_unsupported_filenames(
    filename: str,
    expected_error: str,
) -> None:
    with pytest.raises(ValueError, match=expected_error):
        validate_and_extract_upload(
            filename=filename,
            content_bytes=b"# Safe content",
        )


def test_validate_and_extract_upload_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        validate_and_extract_upload(
            filename="runbook.md",
            content_bytes=b"",
        )


def test_validate_and_extract_upload_rejects_whitespace_only_content() -> None:
    with pytest.raises(ValueError, match="must contain readable text"):
        validate_and_extract_upload(
            filename="runbook.md",
            content_bytes=b" \n\t ",
        )


def test_validate_and_extract_upload_rejects_non_utf8_text_content() -> None:
    with pytest.raises(ValueError, match="must use UTF-8 encoding"):
        validate_and_extract_upload(
            filename="runbook.txt",
            content_bytes=b"\xff\xfe",
        )


def test_validate_and_extract_upload_rejects_oversized_content() -> None:
    with pytest.raises(ValueError, match="document-upload limit"):
        validate_and_extract_upload(
            filename="runbook.txt",
            content_bytes=b"x" * (MAX_DOCUMENT_UPLOAD_BYTES + 1),
        )


def test_validate_and_extract_upload_assigns_plain_text_content_type() -> None:
    result = validate_and_extract_upload(
        filename="Checkout Notes.txt",
        content_bytes=b"Inspect Redis eviction metrics.",
    )

    assert result.source_path == "uploads/checkout-notes.txt"
    assert result.content_type == "text/plain"


def test_validate_and_extract_upload_accepts_pdf_and_docx_content_types() -> None:
    pdf_result = validate_and_extract_upload(
        filename="Redis Report.pdf",
        content_bytes=make_pdf_bytes(),
    )
    docx_result = validate_and_extract_upload(
        filename="Redis Report.docx",
        content_bytes=make_docx_bytes(),
    )

    assert pdf_result.source_path == "uploads/redis-report.pdf"
    assert pdf_result.content_type == "application/pdf"
    assert "[PDF page 1]" in pdf_result.content

    assert docx_result.source_path == "uploads/redis-report.docx"
    assert docx_result.content_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "# DOCX Redis Investigation" in docx_result.content
