# ── PRANA Bootstrap — run ONCE before any other terraform ─────────────────────
# Creates the prerequisites that prod/main.tf depends on:
#   1. S3 bucket for Terraform state (with versioning + encryption)
#   2. DynamoDB table for Terraform state locking
#   3. GitHub Actions OIDC provider
#   4. IAM deploy role (assumed by GitHub Actions via OIDC)
#
# HOW TO RUN (Start-Installation.ps1 does this automatically):
#   cd terraform/bootstrap
#   terraform init
#   terraform apply -var="aws_account_id=YOUR_ACCOUNT_ID" -var="github_repo=nshah12/PRANA"

terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws"; version = "~> 5.0" }
    tls = { source = "hashicorp/tls"; version = "~> 4.0" }
  }
  # Bootstrap uses LOCAL state — it creates the remote state backend
}

provider "aws" {
  region = var.aws_region
  default_tags { tags = { Project = "prana", ManagedBy = "terraform-bootstrap" } }
}

variable "aws_region"    { type = string; default = "ap-south-1" }
variable "aws_account_id" { type = string }
variable "github_repo"   { type = string; default = "nshah12/PRANA" }
variable "environment"   { type = string; default = "prod" }

locals {
  state_bucket    = "prana-terraform-state-${var.environment}"
  locks_table     = "prana-terraform-locks"
  deploy_role     = "prana-github-deploy"
}

# ── 1. S3 Terraform state bucket ──────────────────────────────────────────────

resource "aws_s3_bucket" "terraform_state" {
  bucket        = local.state_bucket
  force_destroy = false
  tags          = { Name = local.state_bucket, Purpose = "terraform-state" }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── 2. DynamoDB state lock table ──────────────────────────────────────────────

resource "aws_dynamodb_table" "terraform_locks" {
  name         = local.locks_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = { Name = local.locks_table, Purpose = "terraform-state-lock" }
}

# ── 3. GitHub Actions OIDC provider ───────────────────────────────────────────

data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]
}

# ── 4. IAM deploy role (assumed by GitHub Actions) ────────────────────────────

data "aws_iam_policy_document" "github_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = local.deploy_role
  assume_role_policy = data.aws_iam_policy_document.github_trust.json
  tags               = { Name = local.deploy_role, Purpose = "github-actions-deploy" }
}

resource "aws_iam_role_policy" "github_deploy_permissions" {
  name = "prana-deploy-permissions"
  role = aws_iam_role.github_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECRAuth"
        Effect = "Allow"
        Action = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "ECRPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ]
        Resource = "arn:aws:ecr:${var.aws_region}:${var.aws_account_id}:repository/prana-${var.environment}/*"
      },
      {
        Sid    = "ECSDeployRead"
        Effect = "Allow"
        Action = [
          "ecs:DescribeTaskDefinition",
          "ecs:DescribeServices",
          "ecs:DescribeTasks",
          "ecs:ListTasks"
        ]
        Resource = "*"
      },
      {
        Sid    = "ECSDeployWrite"
        Effect = "Allow"
        Action = [
          "ecs:RegisterTaskDefinition",
          "ecs:UpdateService",
          "ecs:RunTask"
        ]
        Resource = "*"
      },
      {
        Sid    = "PassRole"
        Effect = "Allow"
        Action = ["iam:PassRole"]
        Resource = "arn:aws:iam::${var.aws_account_id}:role/prana-*"
      },
      {
        Sid    = "S3KongConfig"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject"]
        Resource = "arn:aws:s3:::prana-*-documents/config/*"
      },
      {
        Sid    = "SecretsRead"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:prana/*"
      }
    ]
  })
}

# ── Outputs ───────────────────────────────────────────────────────────────────

output "deploy_role_arn" {
  value       = aws_iam_role.github_deploy.arn
  description = "Set as GitHub secret AWS_DEPLOY_ROLE_ARN"
}

output "state_bucket" {
  value       = aws_s3_bucket.terraform_state.bucket
  description = "Terraform state bucket name"
}

output "locks_table" {
  value       = aws_dynamodb_table.terraform_locks.name
  description = "Terraform state lock table name"
}
