# ── KMS module — AWS KMS backend ─────────────────────────────────────────────
# TO SWAP TO HASHICORP VAULT:
#   Replace aws_kms_key with vault_transit_secret_backend_key.
#   Update outputs.tf to emit vault_path instead of key_arn.
#   encryption_service.py already reads key reference from env var — zero app change.

locals {
  name = var.tenant_id != "" ? "prana/${var.environment}/tenant/${var.tenant_id}/${var.key_purpose}" : "prana/${var.environment}/platform/${var.key_purpose}"
}

resource "aws_kms_key" "prana" {
  description             = "PRANA ${var.environment} — ${var.key_purpose}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  rotation_period_in_days = var.key_rotation_days
  multi_region            = true  # replicated to ap-south-2 automatically

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "KeyAdmins"
        Effect    = "Allow"
        Principal = { AWS = var.admin_role_arns }
        Action    = ["kms:Create*", "kms:Describe*", "kms:Enable*", "kms:List*",
                     "kms:Put*", "kms:Update*", "kms:Revoke*", "kms:Disable*",
                     "kms:Get*", "kms:Delete*", "kms:ScheduleKeyDeletion", "kms:CancelKeyDeletion"]
        Resource  = "*"
      },
      {
        Sid       = "KeyUsage"
        Effect    = "Allow"
        Principal = { AWS = var.usage_role_arns }
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*",
                     "kms:GenerateDataKey*", "kms:DescribeKey"]
        Resource  = "*"
      }
    ]
  })

  tags = merge(var.tags, {
    Name        = local.name
    key_purpose = var.key_purpose
    tenant_id   = var.tenant_id
  })
}

resource "aws_kms_alias" "prana" {
  name          = "alias/${replace(local.name, "/", "-")}"
  target_key_id = aws_kms_key.prana.key_id
}

# ── Multi-region replica (ap-south-2) ─────────────────────────────────────────

resource "aws_kms_replica_key" "prana_hyderabad" {
  provider                = aws.ap-south-2
  primary_key_arn         = aws_kms_key.prana.arn
  description             = "PRANA ${var.environment} — ${var.key_purpose} (ap-south-2 replica)"
  deletion_window_in_days = 30
  enabled                 = true
  tags                    = var.tags
}
