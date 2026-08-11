from app.services.ingestion import calculate_content_sha256, extract_markdown_title


def test_content_hash_is_deterministic() -> None:
    content = "# Checkout latency runbook"

    assert calculate_content_sha256(content) == calculate_content_sha256(content)
    assert len(calculate_content_sha256(content)) == 64


def test_content_hash_changes_when_content_changes() -> None:
    original = calculate_content_sha256("checkout latency")
    changed = calculate_content_sha256("checkout latency increased")

    assert original != changed


def test_extract_markdown_title_uses_first_level_one_heading() -> None:
    content = "Intro text\n\n# Checkout Latency Runbook\n\nMore details"

    assert extract_markdown_title(content, "Fallback") == "Checkout Latency Runbook"


def test_extract_markdown_title_uses_fallback_without_a_heading() -> None:
    assert extract_markdown_title("No heading here", "Fallback Title") == "Fallback Title"
