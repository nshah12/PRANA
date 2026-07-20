# ── ECR outputs — keyed by service name ───────────────────────────────────────
# Usage: module.ecr.repository_urls["prana-api"]

output "repository_urls" {
  description = "Map of service name → ECR repository URL"
  value       = { for k, v in aws_ecr_repository.service : k => v.repository_url }
}

output "repository_arns" {
  description = "Map of service name → ECR repository ARN (for IAM policies)"
  value       = { for k, v in aws_ecr_repository.service : k => v.arn }
}

output "registry_id" {
  description = "AWS account ID that owns the registry"
  value       = data.aws_caller_identity.current.account_id
}
