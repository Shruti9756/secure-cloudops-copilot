import pytest

from app.services.document_access import (
    ALL_DOCUMENT_ACCESS_LEVELS,
    ORGANIZATION_DOCUMENT_ACCESS,
    RESTRICTED_DOCUMENT_ACCESS,
    get_readable_document_access_levels,
    normalize_document_access_levels,
)


@pytest.mark.parametrize(
    ("role", "expected_access_levels"),
    [
        ("admin", {ORGANIZATION_DOCUMENT_ACCESS, RESTRICTED_DOCUMENT_ACCESS}),
        ("manager", {ORGANIZATION_DOCUMENT_ACCESS, RESTRICTED_DOCUMENT_ACCESS}),
        ("engineer", {ORGANIZATION_DOCUMENT_ACCESS}),
    ],
)
def test_document_access_levels_match_the_membership_role(
    role: str,
    expected_access_levels: set[str],
) -> None:
    assert get_readable_document_access_levels(role) == expected_access_levels


def test_unknown_role_is_rejected_fail_closed() -> None:
    with pytest.raises(ValueError, match="Document access role is not supported"):
        get_readable_document_access_levels("unexpected-role")


def test_normalize_document_access_levels_returns_immutable_supported_levels() -> None:
    normalized_levels = normalize_document_access_levels(
        {ORGANIZATION_DOCUMENT_ACCESS, RESTRICTED_DOCUMENT_ACCESS}
    )

    assert normalized_levels == ALL_DOCUMENT_ACCESS_LEVELS
    assert isinstance(normalized_levels, frozenset)


@pytest.mark.parametrize(
    "document_access_levels",
    [
        set(),
        {"unsupported"},
    ],
)
def test_normalize_document_access_levels_rejects_invalid_levels(
    document_access_levels: set[str],
) -> None:
    with pytest.raises(ValueError):
        normalize_document_access_levels(document_access_levels)  # type: ignore[arg-type]
