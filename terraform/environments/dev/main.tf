# ── PRANA Dev — single region, minimal cost, no HA ───────────────────────────
# Uses docker-compose for Kafka + Redis locally.
# This file provisions only the cloud resources dev needs:
#   - S3 bucket (real S3 — MinIO locally)
#   - KMS key (real KMS — use localstack KMS locally)
#   - ECR repos for images
# Kafka and Redis in dev = docker-compose, NOT MSK/ElastiCache.

terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws"; version = "~> 5.0" }
  }
  backend "local" {
    path = "dev.tfstate"
  }
}

provider "aws" {
  region = "ap-south-1"
  default_tags { tags = { Environment = "dev", Project = "prana", ManagedBy = "terraform" } }
}

# Dev S3 — real bucket, small lifecycle
resource "aws_s3_bucket" "dev_documents" {
  bucket        = "prana-dev-documents-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "dev_documents" {
  bucket                  = aws_s3_bucket.dev_documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Dev KMS — real key, lower rotation
resource "aws_kms_key" "dev_platform" {
  description             = "PRANA dev — platform secret"
  deletion_window_in_days = 7
  enable_key_rotation     = false
}

resource "aws_kms_alias" "dev_platform" {
  name          = "alias/prana-dev-platform-secret"
  target_key_id = aws_kms_key.dev_platform.key_id
}

# ECR repos — shared dev images
resource "aws_ecr_repository" "api"  { name = "prana/api";  image_tag_mutability = "MUTABLE" }
resource "aws_ecr_repository" "ai"   { name = "prana/ai";   image_tag_mutability = "MUTABLE" }
resource "aws_ecr_repository" "ask"  { name = "prana/ask";  image_tag_mutability = "MUTABLE" }

data "aws_caller_identity" "current" {}

output "documents_bucket"       { value = aws_s3_bucket.dev_documents.bucket }
output "platform_secret_key_arn" { value = aws_kms_key.dev_platform.arn }
output "api_ecr_url"             { value = aws_ecr_repository.api.repository_url }
output "ai_ecr_url"              { value = aws_ecr_repository.ai.repository_url }
output "ask_ecr_url"             { value = aws_ecr_repository.ask.repository_url }

# For dev: Kafka + Redis run via docker-compose
# Set in .env.dev:
#   KAFKA_BOOTSTRAP_SERVERS=localhost:9092
#   REDIS_URL=redis://localhost:6379
