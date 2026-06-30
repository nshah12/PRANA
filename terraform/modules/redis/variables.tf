# ── Redis module variables ────────────────────────────────────────────────────
# TO SWAP TO REDIS ENTERPRISE CLOUD:
#   Replace main.tf with rediscloud_* resources. outputs.tf stays identical.

variable "cluster_name" { type = string }
variable "environment"  { type = string }
variable "vpc_id"       { type = string }
variable "subnet_ids"   { type = list(string) }

variable "allowed_security_group_ids" {
  type = list(string)
}

variable "node_type" {
  type    = string
  default = "cache.r7g.large"
  # prod: cache.r7g.2xlarge
  # dev:  cache.t4g.micro
}

variable "num_cache_clusters" {
  type    = number
  default = 2  # prod: 2 (primary + replica per region)
}

variable "enable_multi_az" {
  type    = bool
  default = true
}

variable "enable_global_datastore" {
  type    = bool
  default = false
  # true in prod — links ap-south-1 and ap-south-2 clusters
}

variable "global_replication_group_id" {
  type    = string
  default = ""
  # ID of the primary region's global datastore group (set in secondary region)
}

variable "tags" {
  type    = map(string)
  default = {}
}
