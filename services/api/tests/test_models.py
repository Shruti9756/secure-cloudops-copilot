from app.db.models import AuditEvent, DocumentChunk, KnowledgeDocument, Tenant


def test_knowledge_document_belongs_to_a_tenant() -> None:
    foreign_key_targets = {
        foreign_key.target_fullname for foreign_key in KnowledgeDocument.__table__.foreign_keys
    }

    assert Tenant.__tablename__ == "tenants"
    assert "tenants.id" in foreign_key_targets


def test_document_source_path_is_unique_within_a_tenant() -> None:
    constraint_names = {constraint.name for constraint in KnowledgeDocument.__table__.constraints}

    assert "uq_knowledge_documents_tenant_source_path" in constraint_names


def test_document_chunk_belongs_to_a_document() -> None:
    foreign_key_targets = {
        foreign_key.target_fullname for foreign_key in DocumentChunk.__table__.foreign_keys
    }

    assert KnowledgeDocument.__tablename__ == "knowledge_documents"
    assert "knowledge_documents.id" in foreign_key_targets


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


def test_audit_event_preserves_safe_tenant_scoped_security_metadata() -> None:
    tenant_foreign_key = next(iter(AuditEvent.__table__.foreign_keys))
    audit_column_names = set(AuditEvent.__table__.c.keys())
    audit_index_names = {index.name for index in AuditEvent.__table__.indexes}

    assert tenant_foreign_key.target_fullname == "tenants.id"
    assert tenant_foreign_key.ondelete == "SET NULL"
    assert AuditEvent.__table__.c.tenant_id.nullable is True
    assert AuditEvent.__table__.c["metadata"].name == "metadata"
    assert {"question", "answer", "content"}.isdisjoint(audit_column_names)
    assert "ix_audit_events_event_type" in audit_index_names
    assert "ix_audit_events_tenant_created_at" in audit_index_names
