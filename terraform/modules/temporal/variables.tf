variable "environment"  { type = string }
variable "region"       { type = string }
variable "vpc_id"       { type = string }
variable "subnet_ids"   { type = list(string) }

variable "temporal_sg_id" {
  type        = string
  description = "Security group for Temporal ECS tasks"
}

variable "execution_role_arn" {
  type        = string
  description = "ECS task execution role ARN (shared with compute module)"
}

variable "db_url_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for YugabyteDB connection string (Temporal persistence)"
}

variable "temporal_image" {
  type    = string
  default = "temporalio/auto-setup:1.24"
  description = "Temporal server image — auto-setup runs schema migrations on start"
}

variable "temporal_ui_image" {
  type    = string
  default = "temporalio/ui:2.26.2"
}

variable "server_cpu"    { type = number; default = 1024 }
variable "server_memory" { type = number; default = 2048 }
variable "server_count"  { type = number; default = 2 }

variable "ui_cpu"    { type = number; default = 256 }
variable "ui_memory" { type = number; default = 512 }

variable "api_sg_id" {
  type        = string
  description = "prana-api SG — allowed to connect to Temporal frontend (7233)"
}

variable "tags" {
  type    = map(string)
  default = {}
}
