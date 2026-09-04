from dataclasses import dataclass
from typing import Any, Protocol

import jwt
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

COGNITO_AUTHENTICATION_FAILURE_MESSAGE = "Authentication credentials are invalid or expired."
COGNITO_IDENTITY_PROVIDER_UNAVAILABLE_MESSAGE = (
    "Identity service is temporarily unavailable. Try again later."
)

_EXPECTED_SIGNING_ALGORITHM = "RS256"
_EXPECTED_TOKEN_USE = "access"


class CognitoInvalidAccessTokenError(PermissionError):
    """Raised when an untrusted token fails Cognito access-token validation."""


class CognitoJwksUnavailableError(RuntimeError):
    """Raised when Cognito's public signing keys cannot be reached."""


class JwkSigningKey(Protocol):
    """The small portion of a PyJWT signing key needed by this verifier."""

    @property
    def key(self) -> Any: ...


class JwksClient(Protocol):
    """Allows tests to provide a local signing-key source instead of AWS."""

    def get_signing_key_from_jwt(self, token: str) -> JwkSigningKey: ...


@dataclass(frozen=True)
class VerifiedCognitoAccessToken:
    """Claims safe to use only after signature and required-claim verification."""

    subject: str
    issuer: str
    app_client_id: str


class CognitoAccessTokenVerifier:
    """Verify Cognito access tokens against the user pool's public JWKS keys."""

    def __init__(
        self,
        *,
        issuer: str,
        app_client_id: str,
        jwks_client: JwksClient | None = None,
    ) -> None:
        self._issuer = _require_non_empty_configuration_value(
            issuer,
            setting_name="Cognito issuer",
        ).rstrip("/")
        self._app_client_id = _require_non_empty_configuration_value(
            app_client_id,
            setting_name="Cognito app client ID",
        )
        self._jwks_client = jwks_client or PyJWKClient(
            f"{self._issuer}/.well-known/jwks.json",
            cache_keys=True,
        )

    def verify(self, access_token: str) -> VerifiedCognitoAccessToken:
        """Return verified claims or fail closed without trusting token contents."""

        token = _require_non_empty_access_token(access_token)

        try:
            unverified_header = jwt.get_unverified_header(token)
        except InvalidTokenError as error:
            raise CognitoInvalidAccessTokenError(COGNITO_AUTHENTICATION_FAILURE_MESSAGE) from error

        # Reject algorithm-confusion attempts before selecting any remote key.
        if unverified_header.get("alg") != _EXPECTED_SIGNING_ALGORITHM:
            raise CognitoInvalidAccessTokenError(COGNITO_AUTHENTICATION_FAILURE_MESSAGE)

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                # Pass the concrete public key, not the PyJWK wrapper.
                algorithms=[_EXPECTED_SIGNING_ALGORITHM],
                issuer=self._issuer,
                key=signing_key.key,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "iss",
                        "sub",
                        "token_use",
                        "client_id",
                    ],
                    # Cognito access tokens use client_id, not the ID-token aud claim.
                    "verify_aud": False,
                },
            )
        except PyJWKClientConnectionError as error:
            raise CognitoJwksUnavailableError(
                COGNITO_IDENTITY_PROVIDER_UNAVAILABLE_MESSAGE
            ) from error
        except (InvalidTokenError, PyJWKClientError, TypeError, ValueError) as error:
            raise CognitoInvalidAccessTokenError(COGNITO_AUTHENTICATION_FAILURE_MESSAGE) from error

        if claims.get("token_use") != _EXPECTED_TOKEN_USE:
            raise CognitoInvalidAccessTokenError(COGNITO_AUTHENTICATION_FAILURE_MESSAGE)

        if claims.get("client_id") != self._app_client_id:
            raise CognitoInvalidAccessTokenError(COGNITO_AUTHENTICATION_FAILURE_MESSAGE)

        subject = claims.get("sub")

        if not isinstance(subject, str) or not subject.strip():
            raise CognitoInvalidAccessTokenError(COGNITO_AUTHENTICATION_FAILURE_MESSAGE)

        return VerifiedCognitoAccessToken(
            subject=subject,
            issuer=self._issuer,
            app_client_id=self._app_client_id,
        )


def _require_non_empty_configuration_value(value: str, *, setting_name: str) -> str:
    """Reject incomplete server configuration before processing any request."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{setting_name} must be configured")

    return value.strip()


def _require_non_empty_access_token(value: str) -> str:
    """Reject absent or malformed bearer-token content before JWKS access."""

    if not isinstance(value, str) or not value.strip():
        raise CognitoInvalidAccessTokenError(COGNITO_AUTHENTICATION_FAILURE_MESSAGE)

    return value.strip()
