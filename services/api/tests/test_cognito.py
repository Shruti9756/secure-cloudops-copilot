from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from jwt.exceptions import PyJWKClientConnectionError

from app.infrastructure.cognito import (
    COGNITO_AUTHENTICATION_FAILURE_MESSAGE,
    CognitoAccessTokenVerifier,
    CognitoInvalidAccessTokenError,
    CognitoJwksUnavailableError,
)

ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_OcopA6PcP"
APP_CLIENT_ID = "4nqh1m0r6lfp0uqbvtu679uq0a"


class FakeJwksClient:
    """Return a local public key so tests never call Cognito or the internet."""

    def __init__(self, public_key: Any) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        return SimpleNamespace(key=self._public_key)


class UnavailableJwksClient:
    """Model a temporary failure while fetching Cognito public signing keys."""

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        raise PyJWKClientConnectionError("Cognito JWKS endpoint is unavailable")


@pytest.fixture
def private_key() -> RSAPrivateKey:
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


def make_access_token(
    private_key: RSAPrivateKey,
    *,
    claim_overrides: dict[str, object] | None = None,
) -> str:
    """Create a locally signed Cognito-shaped test token."""

    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": "cognito-user-subject-123",
        "iss": ISSUER,
        "client_id": APP_CLIENT_ID,
        "token_use": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }

    if claim_overrides is not None:
        claims.update(claim_overrides)

    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "local-test-signing-key"},
    )


def make_verifier(private_key: RSAPrivateKey) -> CognitoAccessTokenVerifier:
    return CognitoAccessTokenVerifier(
        issuer=ISSUER,
        app_client_id=APP_CLIENT_ID,
        jwks_client=FakeJwksClient(private_key.public_key()),
    )


def test_verifier_accepts_a_valid_cognito_access_token(
    private_key: RSAPrivateKey,
) -> None:
    token = make_access_token(private_key)

    result = make_verifier(private_key).verify(token)

    assert result.subject == "cognito-user-subject-123"
    assert result.issuer == ISSUER
    assert result.app_client_id == APP_CLIENT_ID


def test_verifier_rejects_an_id_token(
    private_key: RSAPrivateKey,
) -> None:
    token = make_access_token(
        private_key,
        claim_overrides={"token_use": "id"},
    )

    with pytest.raises(
        CognitoInvalidAccessTokenError,
        match=COGNITO_AUTHENTICATION_FAILURE_MESSAGE,
    ):
        make_verifier(private_key).verify(token)


def test_verifier_rejects_a_token_for_another_browser_client(
    private_key: RSAPrivateKey,
) -> None:
    token = make_access_token(
        private_key,
        claim_overrides={"client_id": "different-browser-client"},
    )

    with pytest.raises(
        CognitoInvalidAccessTokenError,
        match=COGNITO_AUTHENTICATION_FAILURE_MESSAGE,
    ):
        make_verifier(private_key).verify(token)


def test_verifier_rejects_an_expired_token(
    private_key: RSAPrivateKey,
) -> None:
    now = datetime.now(UTC)
    expired_token = jwt.encode(
        {
            "sub": "cognito-user-subject-123",
            "iss": ISSUER,
            "client_id": APP_CLIENT_ID,
            "token_use": "access",
            "iat": now - timedelta(minutes=10),
            "exp": now - timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "local-test-signing-key"},
    )

    with pytest.raises(
        CognitoInvalidAccessTokenError,
        match=COGNITO_AUTHENTICATION_FAILURE_MESSAGE,
    ):
        make_verifier(private_key).verify(expired_token)


def test_verifier_rejects_a_non_rs256_token_without_using_jwks(
    private_key: RSAPrivateKey,
) -> None:
    token = jwt.encode(
        {
            "sub": "cognito-user-subject-123",
            "iss": ISSUER,
            "client_id": APP_CLIENT_ID,
            "token_use": "access",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "not-a-cognito-signing-key-with-at-least-32-bytes",
        algorithm="HS256",
        headers={"kid": "untrusted-key"},
    )

    with pytest.raises(
        CognitoInvalidAccessTokenError,
        match=COGNITO_AUTHENTICATION_FAILURE_MESSAGE,
    ):
        make_verifier(private_key).verify(token)


def test_verifier_reports_a_jwks_outage_without_accepting_the_token(
    private_key: RSAPrivateKey,
) -> None:
    # This is a well-formed RS256 token, so verification reaches the JWKS client.
    token = make_access_token(private_key)
    verifier = CognitoAccessTokenVerifier(
        issuer=ISSUER,
        app_client_id=APP_CLIENT_ID,
        jwks_client=UnavailableJwksClient(),
    )

    with pytest.raises(CognitoJwksUnavailableError):
        verifier.verify(token)
