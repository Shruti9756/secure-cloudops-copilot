from app.db.models import KnowledgeDocument, Tenant


def test_knowledge_document_belongs_to_a_tenant() -> None:
    foreign_key_targets = {
        foreign_key.target_fullname for foreign_key in KnowledgeDocument.__table__.foreign_keys
    }

    assert Tenant.__tablename__ == "tenants"
    assert "tenants.id" in foreign_key_targets


def test_document_source_path_is_unique_within_a_tenant() -> None:
    constraint_names = {constraint.name for constraint in KnowledgeDocument.__table__.constraints}

    assert "uq_knowledge_documents_tenant_source_path" in constraint_names
