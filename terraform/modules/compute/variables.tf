# ── Compute module variables ──────────────────────────────────────────────────
# Defines ECS task definitions for the 3 PRANA services.
# Deployment boundary is enforced here: separate task definitions, separate
# task roles, separate log groups. prana-ai and prana-ask NEVER share
# a task definition with prana-api.

variable "environment"    { type = string }
variable "region"         { type = string }
variable "vpc_id"         { type = string }
variable "subnet_ids"     { type = list(string) }

variable "api_sg_id"  { type = string }
variable "ai_sg_id"   { type = string }
variable "ask_sg_id"  { type = string }

variable "api_image"  { type = string; description = "ECR image URI for prana-api" }
variable "ai_image"   { type = string; description = "ECR image URI for prana-ai" }
variable "ask_image"  { type = string; description = "ECR image URI for prana-ask" }

# Secrets injected as env vars — values come from Secrets Manager / KMS outputs
variable "api_secrets" {
  type        = map(string)
  description = "Map of env var name → Secrets Manager ARN for prana-api"
  sensitive   = true
}

variable "ai_secrets" {
  type      = map(string)
  sensitive = true
}

variable "ask_secrets" {
  type      = map(string)
  sensitive = true
}

variable "api_cpu"    { type = number; default = 1024 }
variable "api_memory" { type = number; default = 2048 }
variable "api_count"  { type = number; default = 2 }

# prana-ai needs GPU — use EC2 launch type with p3/g4dn instances
variable "ai_instance_type"  { type = string; default = "g4dn.xlarge" }
variable "ai_count"          { type = number; default = 1 }

variable "ask_instance_type" { type = string; default = "g4dn.xlarge" }
variable "ask_count"         { type = number; default = 1 }

variable "tags" { type = map(string); default = {} }
