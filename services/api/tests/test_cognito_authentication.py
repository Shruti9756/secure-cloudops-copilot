from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.infrastructure.cognito import (
    COGNITO_AUTHENTICATION_FAILURE_MESSAGE,
    COGNITO_IDENTITY_PROVIDER_UNAVAILABLE_MESSAGE,
    CognitoJwksUnavailableError,
    VerifiedCognitoAccessToken,
)
from app.main import get_current_principal
from app.services.authorization import AuthenticatedPrincipal
from app.services.cognito_identity import CognitoUserNotProvisionedError

ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example"
APP_CLIENT_ID = "example-browser-client-id"


def make_request(authorization_header: str | None = None) -> Request:
    """Build a minimal request without starting an HTTP server."""

    headers: list[tuple[bytes, bytes]] = []

    if authorization_header is not None:
        headers.append((b"authorization", authorization_header.encode("utf-8")))

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/documents",
            "headers": headers,
        }
    )


def use_cognito_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make authentication tests use Cognito mode without changing .env."""

    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: SimpleNamespace(
            identity_provider="cognito",
            cognito_issuer=ISSUER,
            cognito_app_client_id=APP_CLIENT_ID,
        ),
    )


def test_current_principal_uses_verified_cognito_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    verifier = Mock()
    verifier.verify.return_value = VerifiedCognitoAccessToken(
        subject="cognito-stable-subject-123",
        issuer=ISSUER,
        app_client_id=APP_CLIENT_ID,
    )
    expected_principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="cognito-stable-subject-123",
        display_name="Shruti Demo",
    )
    principal_resolver = Mock(return_value=expected_principal)

    use_cognito_settings(monkeypatch)
    monkeypatch.setattr(
        "app.main.get_cognito_access_token_verifier",
        lambda issuer, app_client_id: verifier,
    )
    monkeypatch.setattr(
        "app.main.get_cognito_principal",
        principal_resolver,
    )

    result = get_current_principal(
        request=make_request("Bearer test-access-token"),
        session=session,
    )

    assert result == expected_principal
    verifier.verify.assert_called_once_with("test-access-token")
    principal_resolver.assert_called_once_with(
        session,
        subject="cognito-stable-subject-123",
    )


def test_current_principal_rejects_a_missing_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_cognito_settings(monkeypatch)

    with pytest.raises(HTTPException) as error:
        get_current_principal(
            request=make_request(),
            session=Mock(),
        )

    assert error.value.status_code == 401
    assert error.value.detail == COGNITO_AUTHENTICATION_FAILURE_MESSAGE
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}


def test_current_principal_reports_a_cognito_jwks_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = Mock()
    verifier.verify.side_effect = CognitoJwksUnavailableError(
        COGNITO_IDENTITY_PROVIDER_UNAVAILABLE_MESSAGE
    )

    use_cognito_settings(monkeypatch)
    monkeypatch.setattr(
        "app.main.get_cognito_access_token_verifier",
        lambda issuer, app_client_id: verifier,
    )

    with pytest.raises(HTTPException) as error:
        get_current_principal(
            request=make_request("Bearer test-access-token"),
            session=Mock(),
        )

    assert error.value.status_code == 503
    assert error.value.detail == COGNITO_IDENTITY_PROVIDER_UNAVAILABLE_MESSAGE


def test_current_principal_rejects_an_unprovisioned_cognito_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = Mock()
    verifier.verify.return_value = VerifiedCognitoAccessToken(
        subject="cognito-unknown-subject",
        issuer=ISSUER,
        app_client_id=APP_CLIENT_ID,
    )

    use_cognito_settings(monkeypatch)
    monkeypatch.setattr(
        "app.main.get_cognito_access_token_verifier",
        lambda issuer, app_client_id: verifier,
    )
    monkeypatch.setattr(
        "app.main.get_cognito_principal",
        Mock(
            side_effect=CognitoUserNotProvisionedError("The authenticated user is not provisioned.")
        ),
    )

    with pytest.raises(HTTPException) as error:
        get_current_principal(
            request=make_request("Bearer test-access-token"),
            session=Mock(),
        )

    assert error.value.status_code == 403
    assert error.value.detail == (
        "The authenticated identity is not authorized to access SecureCloudOps."
    )
