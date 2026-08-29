"""Document-level visibility policy inside an already authorized workspace."""

from typing import Literal

from app.services.authorization import MembershipRole

type DocumentAccessLevel = Literal["organization", "restricted"]

ORGANIZATION_DOCUMENT_ACCESS: DocumentAccessLevel = "organization"
RESTRICTED_DOCUMENT_ACCESS: DocumentAccessLevel = "restricted"

READABLE_DOCUMENT_ACCESS_LEVELS_BY_ROLE: dict[
    MembershipRole,
    frozenset[DocumentAccessLevel],
] = {
    "admin": frozenset(
        {
            ORGANIZATION_DOCUMENT_ACCESS,
            RESTRICTED_DOCUMENT_ACCESS,
        }
    ),
    "manager": frozenset(
        {
            ORGANIZATION_DOCUMENT_ACCESS,
            RESTRICTED_DOCUMENT_ACCESS,
        }
    ),
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
