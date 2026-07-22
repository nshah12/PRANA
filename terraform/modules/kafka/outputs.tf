# ── Kafka module outputs — THE SWAP CONTRACT ──────────────────────────────────
# These output names NEVER change regardless of backend (MSK / Confluent / EventHubs).
# Application env vars are set from these outputs.

output "bootstrap_servers" {
  description = "Comma-separated Kafka bootstrap servers — maps to KAFKA_BOOTSTRAP_SERVERS env var"
  value       = aws_msk_cluster.prana.bootstrap_brokers_sasl_iam
  sensitive   = true
}

output "bootstrap_servers_tls" {
  description = "TLS bootstrap servers"
  value       = aws_msk_cluster.prana.bootstrap_brokers_tls
  sensitive   = true
}

output "cluster_arn" {
  description = "MSK cluster ARN — used for IAM policy attachment"
  value       = aws_msk_cluster.prana.arn
}

output "security_group_id" {
  description = "SG ID — attach to compute modules that need broker access"
  value       = aws_security_group.kafka.id
}

output "topic_names" {
  description = "All provisioned topic names"
  value       = keys(kafka_topic.topics)
}
