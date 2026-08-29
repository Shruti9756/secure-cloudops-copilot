"""Validation for the explicit workspace selector on protected API requests."""

from re import fullmatch

WORKSPACE_CONTEXT_HEADER = "X-Workspace-Slug"
WORKSPACE_CONTEXT_REQUIRED_MESSAGE = "A workspace context is required."
WORKSPACE_CONTEXT_INVALID_MESSAGE = "Workspace context is invalid."
WORKSPACE_SLUG_PATTERN = r"[a-z][a-z0-9-]{0,62}"


class WorkspaceContextError(ValueError):
    """Raised when an untrusted workspace selector is missing or malformed."""


def normalize_workspace_slug(raw_workspace_slug: object | None) -> str:
    """Normalize one safe workspace slug before authorization uses it."""
    if not isinstance(raw_workspace_slug, str):
        raise WorkspaceContextError(WORKSPACE_CONTEXT_REQUIRED_MESSAGE)

    normalized_workspace_slug = raw_workspace_slug.strip().casefold()

    if not normalized_workspace_slug:
        raise WorkspaceContextError(WORKSPACE_CONTEXT_REQUIRED_MESSAGE)

    if fullmatch(WORKSPACE_SLUG_PATTERN, normalized_workspace_slug) is None:
        raise WorkspaceContextError(WORKSPACE_CONTEXT_INVALID_MESSAGE)

    return normalized_workspace_slug
