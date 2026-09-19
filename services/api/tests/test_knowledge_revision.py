from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import NoResultFound

from app.services.knowledge_revision import increment_knowledge_revision


def test_increment_knowledge_revision_uses_scoped_database_arithmetic() -> None:
    session = Mock()
    organization_id = uuid4()
    tenant_id = uuid4()
    session.execute.return_value.scalar_one.return_value = 8

    revision = increment_knowledge_revision(
        session,
        organization_id=organization_id,
        tenant_id=tenant_id,
    )

    assert revision == 8
    session.execute.assert_called_once()

    statement = session.execute.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    statement_sql = str(compiled)

    assert "UPDATE tenants SET knowledge_revision=(tenants.knowledge_revision +" in statement_sql
    assert "tenants.id =" in statement_sql
    assert "tenants.organization_id =" in statement_sql
    assert "RETURNING tenants.knowledge_revision" in statement_sql
    assert tenant_id in compiled.params.values()
    assert organization_id in compiled.params.values()
    assert 1 in compiled.params.values()

    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_increment_knowledge_revision_does_not_hide_a_missing_workspace() -> None:
    session = Mock()
    session.execute.return_value.scalar_one.side_effect = NoResultFound()

    with pytest.raises(NoResultFound):
        increment_knowledge_revision(
            session,
            organization_id=uuid4(),
            tenant_id=uuid4(),
        )

    session.commit.assert_not_called()
    session.rollback.assert_not_called()
