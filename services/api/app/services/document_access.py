"""Document-level visibility policy inside an already authorized workspace."""

from typing import Literal

from app.services.authorization import MembershipRole

type DocumentAccessLevel = Literal["organization", "restricted"]

ORGANIZATION_DOCUMENT_ACCESS: DocumentAccessLevel = "organization"
RESTRICTED_DOCUMENT_ACCESS: DocumentAccessLevel = "restricted"

ALL_DOCUMENT_ACCESS_LEVELS: frozenset[DocumentAccessLevel] = frozenset(
    {
        ORGANIZATION_DOCUMENT_ACCESS,
        RESTRICTED_DOCUMENT_ACCESS,
    }
)

DEFAULT_DOCUMENT_ACCESS_LEVELS: frozenset[DocumentAccessLevel] = frozenset(
    {
        ORGANIZATION_DOCUMENT_ACCESS,
    }
)

READABLE_DOCUMENT_ACCESS_LEVELS_BY_ROLE: dict[
    MembershipRole,
    frozenset[DocumentAccessLevel],
] = {
    "admin": ALL_DOCUMENT_ACCESS_LEVELS,
    "manager": ALL_DOCUMENT_ACCESS_LEVELS,
    "engineer": frozenset({ORGANIZATION_DOCUMENT_ACCESS}),
}


def get_readable_document_access_levels(
    role: MembershipRole,
) -> frozenset[DocumentAccessLevel]:
    """Return document levels the verified membership role may retrieve."""
    levels = READABLE_DOCUMENT_ACCESS_LEVELS_BY_ROLE.get(role)

    if levels is None:
        raise ValueError("Document access role is not supported")

    return levels
