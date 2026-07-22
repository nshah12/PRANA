# ── KMS module variables ──────────────────────────────────────────────────────
# TO SWAP TO HASHICORP VAULT:
#   Replace main.tf with vault_mount + vault_transit_secret_backend_key.
#   App code already abstracts KMS behind encryption_service.py — zero app changes.

variable "environment"  { type = string }
variable "tenant_id"    { type = string; default = "" }  # empty = platform key

variable "key_purpose" {
  type        = string
  description = "platform_secret | tenant_kek | totp | session"
}

variable "key_rotation_days" {
  type    = number
  default = 365
}

variable "admin_role_arns" {
  type        = list(string)
  description = "IAM roles that can manage (not use) the key"
}

variable "usage_role_arns" {
  type        = list(string)
  description = "IAM roles that can encrypt/decrypt with the key"
}

variable "tags" {
  type    = map(string)
  default = {}
}
