variable "platform_admin_role_arn" { type = string }
variable "api_image"              { type = string }
variable "ai_image"               { type = string }
variable "ask_image"              { type = string }
variable "yugabytedb_password"    { type = string; sensitive = true }
variable "acm_certificate_arn"    { type = string; description = "ACM cert ARN for the API domain — must be in ap-south-1" }
variable "domain_name"           { type = string; description = "Root domain, e.g. prana.in" }
variable "api_subdomain"         { type = string; default = "api"; description = "Subdomain for the gateway, e.g. 'api' → api.prana.in" }
variable "route53_zone_id"       { type = string; description = "Route53 hosted zone ID for domain_name" }
