output "temporal_address" {
  description = "Temporal frontend address for prana-api TEMPORAL_HOST_URL env var"
  value       = "temporal.prana.local:7233"
}

output "temporal_ui_url" {
  description = "Temporal UI (internal — access via VPN or bastion only)"
  value       = "http://temporal.prana.local:8080"
}

output "service_discovery_namespace_id" {
  value = aws_service_discovery_private_dns_namespace.prana.id
}
