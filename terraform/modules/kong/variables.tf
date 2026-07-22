variable "environment"    { type = string }
variable "region"         { type = string }
variable "vpc_id"         { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "public_subnet_ids"  { type = list(string) }
variable "kong_sg_id"    { type = string }
variable "alb_sg_id"     { type = string }
variable "tags"           { type = map(string); default = {} }

# Kong image — use official Kong Gateway image
variable "kong_image" {
  type    = string
  default = "kong/kong-gateway:3.7"
}

variable "kong_cpu"    { type = number; default = 1024 }
variable "kong_memory" { type = number; default = 2048 }
variable "kong_count"  { type = number; default = 2 }

# ACM certificate ARN for ALB TLS termination
variable "acm_certificate_arn" { type = string }

# Upstream service discovery — internal DNS from ECS service discovery
variable "api_upstream_host"  { type = string; description = "Internal DNS for prana-api ECS service" }
variable "ask_upstream_host"  { type = string; description = "Internal DNS for prana-ask ECS service" }

# Secrets — pulled from Secrets Manager by Kong at startup
variable "jwt_secret_arn"  { type = string; description = "Secrets Manager ARN containing JWT signing secret" }
variable "kong_config_s3_bucket" { type = string; description = "S3 bucket where kong.yml is stored" }
variable "kong_config_s3_key"    { type = string; default = "config/kong.yml" }

variable "execution_role_arn" { type = string; description = "ECS task execution role ARN" }
