from unittest.mock import Mock

from app.db.models import Organization, Tenant
from app.services.ingestion import get_or_create_tenant


def test_get_or_create_tenant_creates_an_organization_first() -> None:
    """A fresh database must never create an unowned tenant workspace."""
    session = Mock()

    # First query finds no tenant; second query finds no organization.
    session.scalar.side_effect = [None, None]

    tenant = get_or_create_tenant(
        session=session,
        slug="nimbuscart",
        name="NimbusCart",
    )

    created_organization = session.add.call_args_list[0].args[0]
    created_tenant = session.add.call_args_list[1].args[0]

    assert isinstance(created_organization, Organization)
    assert created_organization.slug == "nimbuscart"
    assert isinstance(created_tenant, Tenant)
    assert created_tenant is tenant
    assert tenant.organization is created_organization
    assert tenant.slug == "nimbuscart"
    assert session.flush.call_count == 2
