# ── PRANA Staging — single region (ap-south-1), production-like but smaller ───
# Same modules as prod, different sizing.
# Purpose: integration tests, load tests, partner HRMS integration testing.

terraform {
  required_version = ">= 1.7"
  required_providers {
    aws   = { source = "hashicorp/aws";  version = "~> 5.0" }
    kafka = { source = "Mongey/kafka";   version = "~> 0.5" }
    random = { source = "hashicorp/random"; version = "~> 3.0" }
  }
  backend "s3" {
    bucket         = "prana-terraform-state-staging"
    key            = "staging/terraform.tfstate"
    region         = "ap-south-1"
    encrypt        = true
    dynamodb_table = "prana-terraform-locks"
  }
}

provider "aws" {
  region = "ap-south-1"
  default_tags { tags = local.common_tags }
}

provider "kafka" {
  bootstrap_servers = [module.kafka.bootstrap_servers]
  tls_enabled       = true
}

locals {
  env = "staging"
  common_tags = {
    Environment = "staging"
    Project     = "prana"
    ManagedBy   = "terraform"
  }
}

module "networking" {
  source      = "../../modules/networking"
  environment = local.env
  region      = "ap-south-1"
  vpc_cidr    = "10.2.0.0/16"
  tags        = local.common_tags
}

module "kms_platform_secret" {
  source          = "../../modules/kms"
  environment     = local.env
  key_purpose     = "platform_secret"
  admin_role_arns = [var.platform_admin_role_arn]
  usage_role_arns = [module.compute.api_task_role_arn, module.compute.ai_task_role_arn]
  tags            = local.common_tags
}

module "kms_totp" {
  source          = "../../modules/kms"
  environment     = local.env
  key_purpose     = "totp"
  admin_role_arns = [var.platform_admin_role_arn]
  usage_role_arns = [module.compute.api_task_role_arn]
  tags            = local.common_tags
}

module "s3" {
  source            = "../../modules/s3"
  environment       = local.env
  kms_key_arn       = module.kms_platform_secret.key_arn
  audit_kms_key_arn = module.kms_platform_secret.key_arn
  tags              = local.common_tags
}

module "kafka" {
  source       = "../../modules/kafka"
  cluster_name = "prana-staging"
  environment  = local.env
  vpc_id       = module.networking.vpc_id
  subnet_ids   = module.networking.private_subnet_ids

  allowed_security_group_ids = [
    module.networking.api_sg_id,
    module.networking.ai_sg_id,
  ]

  broker_instance_type = "kafka.m5.large"   # smaller than prod
  broker_count_per_az  = 1
  broker_storage_gb    = 500
  enable_mirrormaker   = false              # no DR in staging

  tags = local.common_tags
}

module "redis" {
  source       = "../../modules/redis"
  cluster_name = "prana-staging"
  environment  = local.env
  vpc_id       = module.networking.vpc_id
  subnet_ids   = module.networking.private_subnet_ids

  allowed_security_group_ids = [
    module.networking.api_sg_id,
    module.networking.ai_sg_id,
  ]

  node_type               = "cache.r7g.large"
  num_cache_clusters      = 2
  enable_multi_az         = true
  enable_global_datastore = false   # single region in staging

  tags = local.common_tags
}

module "yugabytedb" {
  source      = "../../modules/yugabytedb"
  environment = local.env
  vpc_id      = module.networking.vpc_id
  subnet_ids  = module.networking.private_subnet_ids

  allowed_sg_ids = [module.networking.api_sg_id, module.networking.ai_sg_id]

  node_count         = 3
  node_instance_type = "c5.2xlarge"   # smaller than prod
  node_disk_gb       = 200
  replication_factor = 3
  db_password        = var.yugabytedb_password

  regions = [{ region = "ap-south-1", num_nodes = 3, az = "ap-south-1a" }]

  enable_encryption_at_rest = true
  kms_config_id             = module.kms_platform_secret.key_id
  tags                      = local.common_tags
}

resource "aws_secretsmanager_secret" "db_url"       { name = "prana/staging/yugabytedb/connection-string"; tags = local.common_tags }
resource "aws_secretsmanager_secret_version" "db_url" { secret_id = aws_secretsmanager_secret.db_url.id; secret_string = module.yugabytedb.connection_string }
resource "aws_secretsmanager_secret" "kafka_bootstrap" { name = "prana/staging/kafka/bootstrap-servers"; tags = local.common_tags }
resource "aws_secretsmanager_secret_version" "kafka_bootstrap" { secret_id = aws_secretsmanager_secret.kafka_bootstrap.id; secret_string = module.kafka.bootstrap_servers }
resource "aws_secretsmanager_secret" "s3_bucket"    { name = "prana/staging/s3/documents-bucket"; tags = local.common_tags }
resource "aws_secretsmanager_secret_version" "s3_bucket" { secret_id = aws_secretsmanager_secret.s3_bucket.id; secret_string = module.s3.documents_bucket }

data "aws_caller_identity" "current" {}

# ── Kong API Gateway ──────────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "jwt_secret" {
  name = "prana/staging/jwt/signing-secret"
  tags = local.common_tags
}

module "kong" {
  source      = "../../modules/kong"
  environment = local.env
  region      = "ap-south-1"

  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
  public_subnet_ids  = module.networking.public_subnet_ids
  kong_sg_id         = module.networking.kong_sg_id
  alb_sg_id          = module.networking.alb_sg_id

  acm_certificate_arn   = var.acm_certificate_arn
  api_upstream_host     = "prana-api.staging.internal"
  ask_upstream_host     = "prana-ask.staging.internal"
  jwt_secret_arn        = aws_secretsmanager_secret.jwt_secret.arn
  kong_config_s3_bucket = module.s3.documents_bucket
  kong_config_s3_key    = "config/kong.yml"
  execution_role_arn    = module.compute.execution_role_arn

  kong_count = 1

  tags = local.common_tags
}

module "compute" {
  source      = "../../modules/compute"
  environment = local.env
  region      = "ap-south-1"
  vpc_id      = module.networking.vpc_id
  subnet_ids  = module.networking.private_subnet_ids

  api_sg_id = module.networking.api_sg_id
  ai_sg_id  = module.networking.ai_sg_id
  ask_sg_id = module.networking.ask_sg_id

  api_image = var.api_image
  ai_image  = var.ai_image
  ask_image = var.ask_image

  api_count        = 1
  ai_count         = 1
  ask_count        = 1
  ai_instance_type = "g4dn.xlarge"   # smaller GPU in staging

  kafka_cluster_arn       = module.kafka.cluster_arn
  kafka_cluster_name      = "prana-staging"
  documents_bucket_arn    = module.s3.documents_bucket_arn
  audit_cold_bucket_arn   = module.s3.audit_cold_bucket_arn
  platform_secret_key_arn = module.kms_platform_secret.key_arn
  totp_key_arn            = module.kms_totp.key_arn
  aws_account_id          = data.aws_caller_identity.current.account_id
  aws_region              = "ap-south-1"

  api_secrets = {
    KAFKA_BOOTSTRAP_SERVERS = aws_secretsmanager_secret.kafka_bootstrap.arn
    REDIS_URL               = module.redis.auth_token_secret_arn
    PLATFORM_SECRET_KEY_ARN = module.kms_platform_secret.key_arn
    TOTP_KEY_ARN            = module.kms_totp.key_arn
    S3_DOCUMENTS_BUCKET     = aws_secretsmanager_secret.s3_bucket.arn
    DATABASE_URL            = aws_secretsmanager_secret.db_url.arn
  }

  ai_secrets = {
    KAFKA_BOOTSTRAP_SERVERS = aws_secretsmanager_secret.kafka_bootstrap.arn
    PLATFORM_SECRET_KEY_ARN = module.kms_platform_secret.key_arn
    S3_DOCUMENTS_BUCKET     = aws_secretsmanager_secret.s3_bucket.arn
    DATABASE_URL            = aws_secretsmanager_secret.db_url.arn
  }

  ask_secrets = {
    REDIS_URL    = module.redis.auth_token_secret_arn
    DATABASE_URL = aws_secretsmanager_secret.db_url.arn
  }

  tags = local.common_tags
}

variable "platform_admin_role_arn" { type = string }
variable "api_image"               { type = string }
variable "ai_image"                { type = string }
variable "ask_image"               { type = string }
variable "yugabytedb_password"     { type = string; sensitive = true }
variable "acm_certificate_arn"     { type = string }
variable "domain_name"             { type = string; default = "prana.in" }
variable "api_subdomain"           { type = string; default = "api-staging" }
variable "route53_zone_id"         { type = string }

resource "aws_route53_record" "api" {
  zone_id = var.route53_zone_id
  name    = "${var.api_subdomain}.${var.domain_name}"
  type    = "A"

  alias {
    name                   = module.kong.alb_dns_name
    zone_id                = module.kong.alb_zone_id
    evaluate_target_health = true
  }
}

output "api_cluster_id"    { value = module.compute.cluster_id }
output "api_url"           { value = "https://${var.api_subdomain}.${var.domain_name}" }
output "kafka_bootstrap"   { value = module.kafka.bootstrap_servers; sensitive = true }
output "redis_endpoint"    { value = module.redis.host; sensitive = true }
output "db_endpoint"       { value = module.yugabytedb.cluster_endpoint }
