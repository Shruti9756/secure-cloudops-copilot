from app.db.models import DocumentChunk, KnowledgeDocument, Tenant


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
