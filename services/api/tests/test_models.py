from app.db.models import AuditEvent, DocumentChunk, KnowledgeDocument, Tenant


def test_knowledge_document_has_direct_tenant_and_organization_ownership() -> None:
    foreign_key_targets = {
        foreign_key.target_fullname for foreign_key in KnowledgeDocument.__table__.foreign_keys
    }
    index_names = {index.name for index in KnowledgeDocument.__table__.indexes}

    assert Tenant.__tablename__ == "tenants"
    assert {"tenants.id", "organizations.id"}.issubset(foreign_key_targets)
    assert KnowledgeDocument.__table__.c.organization_id.nullable is False
    assert "ix_knowledge_documents_organization_id" in index_names


def test_document_source_path_is_unique_within_a_tenant() -> None:
    constraint_names = {constraint.name for constraint in KnowledgeDocument.__table__.constraints}

    assert "uq_knowledge_documents_tenant_source_path" in constraint_names


def test_document_chunk_has_direct_document_and_organization_ownership() -> None:
    foreign_key_targets = {
        foreign_key.target_fullname for foreign_key in DocumentChunk.__table__.foreign_keys
    }
    index_names = {index.name for index in DocumentChunk.__table__.indexes}

    assert KnowledgeDocument.__tablename__ == "knowledge_documents"
    assert {"knowledge_documents.id", "organizations.id"}.issubset(foreign_key_targets)
    assert DocumentChunk.__table__.c.organization_id.nullable is False
    assert "ix_document_chunks_organization_id" in index_names


def test_document_chunk_order_is_unique_and_nonnegative() -> None:
    constraint_names = {constraint.name for constraint in DocumentChunk.__table__.constraints}

    assert "uq_document_chunks_document_id_chunk_index" in constraint_names
    assert "ck_document_chunks_chunk_index_nonnegative" in constraint_names
    assert "ck_document_chunks_embedding_token_count_nonnegative" in constraint_names


def test_document_chunk_embedding_is_nullable_and_has_titan_v2_dimensions() -> None:
    embedding_column = DocumentChunk.__table__.c.embedding

    # Existing chunks are backfilled after this migration, so the column begins nullable.
    assert embedding_column.nullable is True
    assert embedding_column.type.dim == 1024


def test_audit_event_preserves_safe_organization_scoped_security_metadata() -> None:
    audit_foreign_keys = {
        foreign_key.target_fullname: foreign_key
        for foreign_key in AuditEvent.__table__.foreign_keys
    }
    audit_column_names = set(AuditEvent.__table__.c.keys())
    audit_index_names = {index.name for index in AuditEvent.__table__.indexes}

    assert audit_foreign_keys["tenants.id"].ondelete == "SET NULL"
    assert audit_foreign_keys["organizations.id"].ondelete == "SET NULL"
    assert AuditEvent.__table__.c.tenant_id.nullable is True
    assert AuditEvent.__table__.c.organization_id.nullable is True
    assert AuditEvent.__table__.c["metadata"].name == "metadata"
    assert {"question", "answer", "content"}.isdisjoint(audit_column_names)
    assert "ix_audit_events_event_type" in audit_index_names
    assert "ix_audit_events_tenant_created_at" in audit_index_names
    assert "ix_audit_events_organization_created_at" in audit_index_names


def test_document_access_level_is_constrained_and_defaults_to_organization() -> None:
    constraint_names = {constraint.name for constraint in KnowledgeDocument.__table__.constraints}
    access_level_column = KnowledgeDocument.__table__.c.access_level

    assert "ck_knowledge_documents_access_level" in constraint_names
    assert access_level_column.nullable is False
    assert str(access_level_column.server_default.arg) == "organization"
