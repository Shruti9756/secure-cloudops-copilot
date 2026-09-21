# This is the existing private bucket used only for redacted extracted text.
resource "aws_s3_bucket" "redacted_document_storage" {
  bucket = var.document_storage_bucket_name

  # Never allow Terraform to delete this learning-project evidence bucket.
  force_destroy = false

  # Project and environment tags come from the provider's default_tags block.
  tags = {
    DataClassification = "synthetic-redacted"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Keep all four S3 public-access protections enabled.
resource "aws_s3_bucket_public_access_block" "redacted_document_storage" {
  bucket = aws_s3_bucket.redacted_document_storage.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true

  lifecycle {
    prevent_destroy = true
  }
}

# Preserve each S3 object version rather than silently overwriting evidence.
resource "aws_s3_bucket_versioning" "redacted_document_storage" {
  bucket = aws_s3_bucket.redacted_document_storage.id

  versioning_configuration {
    status = "Enabled"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Require S3-managed AES-256 encryption for stored redacted text.
resource "aws_s3_bucket_server_side_encryption_configuration" "redacted_document_storage" {
  bucket = aws_s3_bucket.redacted_document_storage.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }

    # This bucket does not use SSE-KMS, so an S3 Bucket Key is unnecessary.
    bucket_key_enabled = false

    # Match AWS's current protection against customer-provided encryption keys.
    blocked_encryption_types = ["SSE-C"]
  }

  lifecycle {
    prevent_destroy = true
  }
}