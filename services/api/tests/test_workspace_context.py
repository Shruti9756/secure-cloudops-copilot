import pytest

from app.services.workspace import (
    WORKSPACE_CONTEXT_INVALID_MESSAGE,
    WORKSPACE_CONTEXT_REQUIRED_MESSAGE,
    WorkspaceContextError,
    normalize_workspace_slug,
)


@pytest.mark.parametrize(
    ("raw_workspace_slug", "expected_workspace_slug"),
    [
        ("nimbuscart", "nimbuscart"),
        ("  NimbusCart  ", "nimbuscart"),
        ("orders-team-2", "orders-team-2"),
    ],
)
def test_normalize_workspace_slug_returns_a_safe_canonical_value(
    raw_workspace_slug: str,
    expected_workspace_slug: str,
) -> None:
    assert normalize_workspace_slug(raw_workspace_slug) == expected_workspace_slug


@pytest.mark.parametrize(
    "raw_workspace_slug",
    [
        None,
        "",
        "   ",
    ],
)
def test_normalize_workspace_slug_rejects_missing_context(
    raw_workspace_slug: object | None,
) -> None:
    with pytest.raises(
        WorkspaceContextError,
        match=WORKSPACE_CONTEXT_REQUIRED_MESSAGE,
    ):
        normalize_workspace_slug(raw_workspace_slug)


@pytest.mark.parametrize(
    "raw_workspace_slug",
    [
        "nimbus_cart",
        "nimbus/cart",
        "-nimbuscart",
        "a" * 64,
    ],
)
def test_normalize_workspace_slug_rejects_unsafe_context(
    raw_workspace_slug: str,
) -> None:
    with pytest.raises(
        WorkspaceContextError,
        match=WORKSPACE_CONTEXT_INVALID_MESSAGE,
    ):
        normalize_workspace_slug(raw_workspace_slug)
