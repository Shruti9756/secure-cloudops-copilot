"""Create the explicit local development identity used before Cognito is added."""

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.services.local_identity import bootstrap_local_development_identity


def main() -> None:
    """Create the local user and its organization membership once, if needed."""
    settings = get_settings()

    if settings.app_env != "development":
        raise RuntimeError("Local identity bootstrap is allowed only when APP_ENV is development.")

    with get_session_factory().begin() as session:
        tenant = session.scalar(
            select(Tenant).where(Tenant.slug == settings.document_processor_tenant_slug)
        )

        if tenant is None:
            raise RuntimeError(
                "The configured local tenant does not exist. "
                "Run the demo-data ingestion before bootstrap."
            )

        result = bootstrap_local_development_identity(
            session,
            tenant=tenant,
            identity_subject=settings.local_development_identity_subject,
            display_name=settings.local_development_identity_display_name,
            role=settings.local_development_identity_role,
        )

    print(
        "Local development identity ready: "
        f"user_created={result.user_created}, "
        f"membership_created={result.membership_created}"
    )


if __name__ == "__main__":
    main()
