# ── S3 module — document storage + audit cold storage ─────────────────────────
# TO SWAP TO AZURE BLOB / GCS:
#   Replace aws_s3_bucket with azurerm_storage_container or google_storage_bucket.
#   App uses boto3 S3 client — swap to Azure SDK in s3_service.py only.
#   Bucket name output stays the same — zero env var changes.

variable "environment"          { type = string }
variable "kms_key_arn"          { type = string }
variable "audit_kms_key_arn"    { type = string }
variable "replication_role_arn" { type = string; default = "" }
variable "replica_bucket_arn"   { type = string; default = "" }
variable "tags"                 { type = map(string); default = {} }

locals {
  docs_bucket  = "prana-${var.environment}-documents"
  audit_bucket = "prana-${var.environment}-audit-cold"
}

# ── Document storage bucket ───────────────────────────────────────────────────

resource "aws_s3_bucket" "documents" {
  bucket        = local.docs_bucket
  force_destroy = var.environment != "prod"
  tags          = merge(var.tags, { Name = local.docs_bucket, purpose = "documents" })
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    id     = "transition-to-ia"
    status = "Enabled"
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 365
      storage_class = "GLACIER_IR"
    }
  }
}

# Cross-region replication to ap-south-2 (prod only)
resource "aws_s3_bucket_replication_configuration" "documents" {
  count  = var.replication_role_arn != "" ? 1 : 0
  bucket = aws_s3_bucket.documents.id
  role   = var.replication_role_arn

  rule {
    id     = "replicate-all"
    status = "Enabled"
    destination {
      bucket        = var.replica_bucket_arn
      storage_class = "STANDARD_IA"
    }
  }
}

# ── Audit cold storage (Apache Iceberg on S3) ─────────────────────────────────
# Hot audit_event rows > 2 years migrate here via AuditArchivalWorkflow

resource "aws_s3_bucket" "audit_cold" {
  bucket        = local.audit_bucket
  force_destroy = false  # NEVER destroy audit cold storage
  tags          = merge(var.tags, { Name = local.audit_bucket, purpose = "audit-cold", retention = "7-years" })
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_cold" {
  bucket = aws_s3_bucket.audit_cold.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.audit_kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "audit_cold" {
  bucket                  = aws_s3_bucket.audit_cold.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Object Lock — WORM for DPDP 7-year audit retention
resource "aws_s3_bucket_object_lock_configuration" "audit_cold" {
  bucket = aws_s3_bucket.audit_cold.id
  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = 7
    }
  }
}

output "documents_bucket" { value = aws_s3_bucket.documents.bucket }
output "documents_bucket_arn" { value = aws_s3_bucket.documents.arn }
output "audit_cold_bucket" { value = aws_s3_bucket.audit_cold.bucket }
output "audit_cold_bucket_arn" { value = aws_s3_bucket.audit_cold.arn }
