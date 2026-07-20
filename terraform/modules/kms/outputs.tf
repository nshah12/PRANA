# ── KMS outputs — THE SWAP CONTRACT ──────────────────────────────────────────
# encryption_service.py reads KEY_ARN from env — same var, different value per cloud

output "key_arn" {
  description = "KMS key ARN — maps to the relevant *_KEY_ARN env var in prana-api"
  value       = aws_kms_key.prana.arn
}

output "key_id" {
  value = aws_kms_key.prana.key_id
}

output "alias_arn" {
  value = aws_kms_alias.prana.arn
}

output "replica_key_arn" {
  description = "ap-south-2 replica key ARN"
  value       = aws_kms_replica_key.prana_hyderabad.arn
}
