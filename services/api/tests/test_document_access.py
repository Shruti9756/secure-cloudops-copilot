import pytest

from app.services.document_access import (
    ORGANIZATION_DOCUMENT_ACCESS,
    RESTRICTED_DOCUMENT_ACCESS,
    get_readable_document_access_levels,
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
