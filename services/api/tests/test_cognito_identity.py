from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.db.models import User
from app.services.cognito_identity import (
    COGNITO_USER_NOT_PROVISIONED_MESSAGE,
    CognitoUserNotProvisionedError,
    get_cognito_principal,
)


def test_get_cognito_principal_returns_database_backed_identity() -> None:
    user = User(
        id=uuid4(),
        identity_subject="cognito-stable-subject-123",
        display_name="Shruti Demo",
    )
    session = Mock()
    session.scalar.return_value = user

    result = get_cognito_principal(
        session,
        subject="cognito-stable-subject-123",
    )

    assert result.user_id == user.id
    assert result.identity_subject == "cognito-stable-subject-123"
    assert result.display_name == "Shruti Demo"
    assert result.authentication_source == "cognito"


def test_get_cognito_principal_rejects_unprovisioned_identity() -> None:
    session = Mock()
    session.scalar.return_value = None

    with pytest.raises(
        CognitoUserNotProvisionedError,
        match="not provisioned",
    ) as error:
        get_cognito_principal(
            session,
            subject="unknown-cognito-subject",
        )

    assert str(error.value) == COGNITO_USER_NOT_PROVISIONED_MESSAGE
