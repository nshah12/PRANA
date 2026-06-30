# ── IAM policies — least-privilege per service ────────────────────────────────
#
# prana-api  → Kafka (produce+consume all topics), KMS (encrypt+decrypt), S3 (read+write), SES, Textract, Secrets
# prana-ai   → Kafka (consume ingest, produce pipeline), KMS (decrypt only), S3 (read only), Textract, Secrets
# prana-ask  → KMS (decrypt only), Secrets (read only). No Kafka. No S3 write.
#
# Separation is enforced in IAM — even if someone cross-imports code, the cloud
# will reject the API call.

variable "kafka_cluster_arn"      { type = string }
variable "kafka_cluster_name"     { type = string }
variable "documents_bucket_arn"   { type = string }
variable "audit_cold_bucket_arn"  { type = string }
variable "platform_secret_key_arn" { type = string }
variable "totp_key_arn"           { type = string }
variable "ses_sender_identity_arn" { type = string; default = "" }
variable "aws_account_id"         { type = string }
variable "aws_region"             { type = string }

locals {
  # Kafka resource ARN patterns for MSK IAM auth
  kafka_cluster_resource  = var.kafka_cluster_arn
  kafka_all_topics        = "arn:aws:kafka:${var.aws_region}:${var.aws_account_id}:topic/${var.kafka_cluster_name}/*/*"
  kafka_all_groups        = "arn:aws:kafka:${var.aws_region}:${var.aws_account_id}:group/${var.kafka_cluster_name}/*/*/*"

  # Per-topic ARNs for prana-ai (only reads ingest, writes pipeline)
  kafka_ingest_topic      = "arn:aws:kafka:${var.aws_region}:${var.aws_account_id}:topic/${var.kafka_cluster_name}/*/prana.ingest.events"
  kafka_pipeline_topic    = "arn:aws:kafka:${var.aws_region}:${var.aws_account_id}:topic/${var.kafka_cluster_name}/*/prana.pipeline.events"
  kafka_audit_topic       = "arn:aws:kafka:${var.aws_region}:${var.aws_account_id}:topic/${var.kafka_cluster_name}/*/prana.audit.events"
  kafka_ai_group          = "arn:aws:kafka:${var.aws_region}:${var.aws_account_id}:group/${var.kafka_cluster_name}/*/prana-ai-*"
}

# ═══════════════════════════════════════════════════════════════════════════════
# prana-api policies
# ═══════════════════════════════════════════════════════════════════════════════

# ── Kafka: full produce + consume all 21 topics ───────────────────────────────

resource "aws_iam_role_policy" "api_kafka" {
  name = "kafka-full"
  role = aws_iam_role.api_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ClusterConnect"
        Effect = "Allow"
        Action = ["kafka-cluster:Connect", "kafka-cluster:AlterCluster", "kafka-cluster:DescribeCluster"]
        Resource = local.kafka_cluster_resource
      },
      {
        Sid    = "TopicAll"
        Effect = "Allow"
        Action = [
          "kafka-cluster:DescribeTopic",
          "kafka-cluster:CreateTopic",
          "kafka-cluster:WriteData",
          "kafka-cluster:ReadData",
        ]
        Resource = local.kafka_all_topics
      },
      {
        Sid    = "ConsumerGroups"
        Effect = "Allow"
        Action = [
          "kafka-cluster:AlterGroup",
          "kafka-cluster:DescribeGroup",
        ]
        Resource = local.kafka_all_groups
      }
    ]
  })
}

# ── KMS: encrypt + decrypt (platform_secret + totp) ──────────────────────────

resource "aws_iam_role_policy" "api_kms" {
  name = "kms-encrypt-decrypt"
  role = aws_iam_role.api_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "PlatformSecret"
        Effect = "Allow"
        Action = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey", "kms:ReEncrypt*"]
        Resource = [var.platform_secret_key_arn]
      },
      {
        Sid    = "TOTPKey"
        Effect = "Allow"
        Action = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
        Resource = [var.totp_key_arn]
      }
    ]
  })
}

# ── S3: read + write documents bucket, NO access to audit cold ────────────────

resource "aws_iam_role_policy" "api_s3" {
  name = "s3-documents"
  role = aws_iam_role.api_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DocumentsReadWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject", "s3:GetObject", "s3:DeleteObject",
          "s3:GetObjectVersion", "s3:ListBucket",
        ]
        Resource = [var.documents_bucket_arn, "${var.documents_bucket_arn}/*"]
      },
      {
        # Audit cold: read-only for DPDP export workflow
        Sid    = "AuditColdReadOnly"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [var.audit_cold_bucket_arn, "${var.audit_cold_bucket_arn}/*"]
      }
    ]
  })
}

# ── SES: send email (OA welcome, DPDP notifications) ─────────────────────────

resource "aws_iam_role_policy" "api_ses" {
  name = "ses-send"
  role = aws_iam_role.api_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SendEmail"
        Effect = "Allow"
        Action = ["ses:SendEmail", "ses:SendRawEmail", "ses:SendTemplatedEmail"]
        Resource = var.ses_sender_identity_arn != "" ? [var.ses_sender_identity_arn] : ["arn:aws:ses:ap-south-1:${var.aws_account_id}:identity/*"]
        Condition = {
          StringLike = { "ses:FromAddress" = "*@prana.in" }
        }
      }
    ]
  })
}

# ── Secrets Manager: read all prana/ secrets ──────────────────────────────────

resource "aws_iam_role_policy" "api_secrets" {
  name = "secrets-read"
  role = aws_iam_role.api_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadPranaSecrets"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:prana/${var.environment}/*"
      }
    ]
  })
}

# ── Textract: OCR fallback ────────────────────────────────────────────────────

resource "aws_iam_role_policy" "api_textract" {
  name = "textract-analyze"
  role = aws_iam_role.api_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Textract"
        Effect   = "Allow"
        Action   = ["textract:AnalyzeDocument", "textract:DetectDocumentText"]
        Resource = "*"
      }
    ]
  })
}

# ═══════════════════════════════════════════════════════════════════════════════
# prana-ai policies — GPU pipeline worker
# ═══════════════════════════════════════════════════════════════════════════════

# ── Kafka: consume ingest.events, produce pipeline.events + audit.events only ─

resource "aws_iam_role_policy" "ai_kafka" {
  name = "kafka-pipeline"
  role = aws_iam_role.ai_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ClusterConnect"
        Effect   = "Allow"
        Action   = ["kafka-cluster:Connect", "kafka-cluster:DescribeCluster"]
        Resource = local.kafka_cluster_resource
      },
      {
        # Read from ingest topic only
        Sid    = "ConsumeIngest"
        Effect = "Allow"
        Action = ["kafka-cluster:DescribeTopic", "kafka-cluster:ReadData"]
        Resource = local.kafka_ingest_topic
      },
      {
        # Write to pipeline + audit topics only
        Sid    = "ProducePipeline"
        Effect = "Allow"
        Action = ["kafka-cluster:DescribeTopic", "kafka-cluster:WriteData"]
        Resource = [local.kafka_pipeline_topic, local.kafka_audit_topic]
      },
      {
        Sid      = "ConsumerGroup"
        Effect   = "Allow"
        Action   = ["kafka-cluster:AlterGroup", "kafka-cluster:DescribeGroup"]
        Resource = local.kafka_ai_group
      }
    ]
  })
}

# ── KMS: decrypt only (for document DEK decryption) ───────────────────────────

resource "aws_iam_role_policy" "ai_kms" {
  name = "kms-decrypt-only"
  role = aws_iam_role.ai_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DecryptOnly"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:DescribeKey", "kms:GenerateDataKey"]
        Resource = [var.platform_secret_key_arn]
        # Explicit deny on Encrypt — prana-ai must NEVER encrypt new PII
        Condition = {
          StringEquals = { "kms:ViaService" = "s3.ap-south-1.amazonaws.com" }
        }
      }
    ]
  })
}

# ── S3: read documents only — prana-ai reads docs but never writes ────────────

resource "aws_iam_role_policy" "ai_s3" {
  name = "s3-read-only"
  role = aws_iam_role.ai_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadDocuments"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = [var.documents_bucket_arn, "${var.documents_bucket_arn}/*"]
      },
      {
        # Explicit deny on write — prana-ai must never write raw docs back
        Sid      = "DenyWrite"
        Effect   = "Deny"
        Action   = ["s3:PutObject", "s3:DeleteObject"]
        Resource = "${var.documents_bucket_arn}/*"
      }
    ]
  })
}

# ── Textract: OCR fallback for prana-ai Stage 02 ─────────────────────────────

resource "aws_iam_role_policy" "ai_textract" {
  name = "textract-analyze"
  role = aws_iam_role.ai_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Textract"
        Effect   = "Allow"
        Action   = ["textract:AnalyzeDocument", "textract:DetectDocumentText"]
        Resource = "*"
      }
    ]
  })
}

# ── Secrets: read prana-ai secrets only ──────────────────────────────────────

resource "aws_iam_role_policy" "ai_secrets" {
  name = "secrets-read"
  role = aws_iam_role.ai_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadAISecrets"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:prana/${var.environment}/ai/*"
      }
    ]
  })
}

# ═══════════════════════════════════════════════════════════════════════════════
# prana-ask policies — RAG chatbot GPU worker
# prana-ask is the most restricted: no Kafka, no S3, no write access anywhere
# ═══════════════════════════════════════════════════════════════════════════════

# ── KMS: decrypt only (for JWT validation secret) ────────────────────────────

resource "aws_iam_role_policy" "ask_kms" {
  name = "kms-decrypt-only"
  role = aws_iam_role.ask_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DecryptOnly"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:DescribeKey"]
        Resource = [var.platform_secret_key_arn]
      }
    ]
  })
}

# ── Secrets: read prana-ask secrets only ─────────────────────────────────────

resource "aws_iam_role_policy" "ask_secrets" {
  name = "secrets-read"
  role = aws_iam_role.ask_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadAskSecrets"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:prana/${var.environment}/ask/*"
      }
    ]
  })
}

# ── Explicit deny policy: prana-ask MUST NOT touch Kafka or S3 ───────────────
# Belt-and-suspenders: even if someone adds an allow elsewhere, this deny wins.

resource "aws_iam_role_policy" "ask_deny_kafka_s3" {
  name = "deny-kafka-and-s3"
  role = aws_iam_role.ask_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DenyKafka"
        Effect   = "Deny"
        Action   = ["kafka-cluster:*", "kafka:*"]
        Resource = "*"
      },
      {
        Sid      = "DenyS3Write"
        Effect   = "Deny"
        Action   = ["s3:PutObject", "s3:DeleteObject", "s3:PutBucketPolicy"]
        Resource = "*"
      }
    ]
  })
}

# ═══════════════════════════════════════════════════════════════════════════════
# Execution role policies (shared — for pulling ECR images + CloudWatch logs)
# ═══════════════════════════════════════════════════════════════════════════════

resource "aws_iam_role_policy" "exec_secrets" {
  for_each = {
    api = aws_iam_role.api_execution.name
    ai  = aws_iam_role.ai_execution.name
    ask = aws_iam_role.ask_execution.name
  }

  name = "exec-secrets-and-ecr"
  role = each.value

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsForEnvInjection"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:prana/${var.environment}/*"
      },
      {
        Sid    = "KMSForSecretDecryption"
        Effect = "Allow"
        Action = ["kms:Decrypt"]
        Resource = [var.platform_secret_key_arn]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/prana/${var.environment}/*"
      }
    ]
  })
}
