# ── Redis outputs — THE SWAP CONTRACT ────────────────────────────────────────

output "endpoint" {
  description = "Redis primary endpoint — maps to REDIS_URL env var"
  value       = "rediss://:${random_password.redis_auth.result}@${aws_elasticache_replication_group.prana.primary_endpoint_address}:6379"
  sensitive   = true
}

output "host" {
  value     = aws_elasticache_replication_group.prana.primary_endpoint_address
  sensitive = true
}

output "port" {
  value = 6379
}

output "auth_token_secret_arn" {
  description = "Secrets Manager ARN for the Redis auth token"
  value       = aws_secretsmanager_secret.redis_auth.arn
}

output "security_group_id" {
  value = aws_security_group.redis.id
}

output "global_replication_group_id" {
  description = "Pass to secondary region module to join Global Datastore"
  value       = length(aws_elasticache_global_replication_group.prana) > 0 ? aws_elasticache_global_replication_group.prana[0].id : ""
}
