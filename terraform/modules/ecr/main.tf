# ── ECR module — one repo per PRANA service ───────────────────────────────────
# Creates: prana-api, prana-ai, prana-ask repositories
# Image scanning on push, AES-256 encryption, lifecycle policy keeps last N images.

locals {
  name_prefix = "prana-${var.environment}"
}

resource "aws_ecr_repository" "service" {
  for_each = toset(var.services)

  name                 = "${local.name_prefix}/${each.key}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(var.tags, { Service = each.key })
}

# Keep the last N images; purge untagged after 1 day
resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last ${var.image_retention_count} tagged images"
        selection = {
          tagStatus   = "tagged"
          tagPrefixList = ["v", "sha-", "main-"]
          countType   = "imageCountMoreThan"
          countNumber = var.image_retention_count
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Purge untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      }
    ]
  })
}

# Allow ECS task execution roles to pull images
data "aws_caller_identity" "current" {}

resource "aws_ecr_repository_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowECSPull"
        Effect = "Allow"
        Principal = {
          AWS = concat(
            ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"],
            [for id in var.allowed_account_ids : "arn:aws:iam::${id}:root"]
          )
        }
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability"
        ]
      }
    ]
  })
}
