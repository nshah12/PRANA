# ── PRANA Production — dual region: ap-south-1 (Mumbai) + ap-south-2 (Hyderabad) ──
#
# TOPOLOGY:
#   ap-south-1 = primary  — all writes, active Kafka, active Redis
#   ap-south-2 = secondary — MirrorMaker 2 sync, Redis Global Datastore replica
#   YugabyteDB = active-active across both regions (26 tables, 256 tablets)
#
# TO RUN:
#   terraform init
#   terraform workspace new prod
#   terraform plan -var-file="prod.tfvars"
#   terraform apply -var-file="prod.tfvars"

terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kafka = {
      # Community Kafka provider — works against MSK AND Confluent Cloud
      # SWAP: change bootstrap_servers in provider config, keep resource blocks identical
      source  = "Mongey/kafka"
      version = "~> 0.5"
    }
    random = { source = "hashicorp/random"; version = "~> 3.0" }
  }

  backend "s3" {
    bucket         = "prana-terraform-state-prod"
    key            = "prod/terraform.tfstate"
    region         = "ap-south-1"
    encrypt        = true
    dynamodb_table = "prana-terraform-locks"
  }
}

# ── Providers ─────────────────────────────────────────────────────────────────

provider "aws" {
  alias  = "mumbai"
  region = "ap-south-1"
  default_tags { tags = local.common_tags }
}

provider "aws" {
  alias  = "hyderabad"
  region = "ap-south-2"
  default_tags { tags = local.common_tags }
}

# Kafka provider points to MSK bootstrap servers
# SWAP TO CONFLUENT: change bootstrap_servers to Confluent endpoint — nothing else changes
provider "kafka" {
  bootstrap_servers = [module.kafka_mumbai.bootstrap_servers]
  tls_enabled       = true
}

locals {
  env = "prod"
  common_tags = {
    Environment = "prod"
    Project     = "prana"
    ManagedBy   = "terraform"
    Compliance  = "DPDP-2023"
  }
}

# ── Networking — ap-south-1 ───────────────────────────────────────────────────

module "networking_mumbai" {
  source      = "../../modules/networking"
  environment = local.env
  region      = "ap-south-1"
  vpc_cidr    = "10.0.0.0/16"
  providers   = { aws = aws.mumbai }
  tags        = local.common_tags
}

module "networking_hyderabad" {
  source      = "../../modules/networking"
  environment = local.env
  region      = "ap-south-2"
  vpc_cidr    = "10.1.0.0/16"
  providers   = { aws = aws.hyderabad }
  tags        = local.common_tags
}

# ── KMS — platform secret + tenant KEK template ───────────────────────────────

module "kms_platform_secret" {
  source      = "../../modules/kms"
  environment = local.env
  key_purpose = "platform_secret"
  admin_role_arns = [var.platform_admin_role_arn]
  usage_role_arns = [
    module.compute_mumbai.api_task_role_arn,
    module.compute_mumbai.ai_task_role_arn,
  ]
  providers = { aws = aws.mumbai, aws.ap-south-2 = aws.hyderabad }
  tags      = local.common_tags
}

module "kms_totp" {
  source      = "../../modules/kms"
  environment = local.env
  key_purpose = "totp"
  admin_role_arns = [var.platform_admin_role_arn]
  usage_role_arns = [module.compute_mumbai.api_task_role_arn]
  providers = { aws = aws.mumbai, aws.ap-south-2 = aws.hyderabad }
  tags      = local.common_tags
}

# ── S3 ────────────────────────────────────────────────────────────────────────

module "s3_mumbai" {
  source            = "../../modules/s3"
  environment       = local.env
  kms_key_arn       = module.kms_platform_secret.key_arn
  audit_kms_key_arn = module.kms_platform_secret.key_arn
  providers         = { aws = aws.mumbai }
  tags              = local.common_tags
}

# ── Kafka — MSK primary (ap-south-1) ─────────────────────────────────────────

module "kafka_mumbai" {
  source       = "../../modules/kafka"
  cluster_name = "prana-prod"
  environment  = local.env
  vpc_id       = module.networking_mumbai.vpc_id
  subnet_ids   = module.networking_mumbai.private_subnet_ids

  allowed_security_group_ids = [
    module.networking_mumbai.api_sg_id,
    module.networking_mumbai.ai_sg_id,
  ]

  broker_instance_type = "kafka.m5.2xlarge"
  broker_count_per_az  = 3
  broker_storage_gb    = 2000

  enable_mirrormaker                   = true
  mirrormaker_source_bootstrap_servers = module.kafka_hyderabad.cluster_arn

  providers = { aws = aws.mumbai }
  tags      = local.common_tags
}

# ── Kafka — MSK secondary (ap-south-2) ───────────────────────────────────────

module "kafka_hyderabad" {
  source       = "../../modules/kafka"
  cluster_name = "prana-prod-dr"
  environment  = local.env
  vpc_id       = module.networking_hyderabad.vpc_id
  subnet_ids   = module.networking_hyderabad.private_subnet_ids

  allowed_security_group_ids = [
    module.networking_hyderabad.api_sg_id,
  ]

  broker_instance_type = "kafka.m5.xlarge"
  broker_count_per_az  = 2
  broker_storage_gb    = 2000

  enable_mirrormaker                   = true
  mirrormaker_source_bootstrap_servers = module.kafka_mumbai.cluster_arn

  providers = { aws = aws.hyderabad }
  tags      = local.common_tags
}

# ── Redis — ElastiCache Global Datastore ──────────────────────────────────────

module "redis_mumbai" {
  source      = "../../modules/redis"
  cluster_name = "prana-prod"
  environment  = local.env
  vpc_id       = module.networking_mumbai.vpc_id
  subnet_ids   = module.networking_mumbai.private_subnet_ids

  allowed_security_group_ids = [
    module.networking_mumbai.api_sg_id,
    module.networking_mumbai.ai_sg_id,
  ]

  node_type               = "cache.r7g.2xlarge"
  num_cache_clusters      = 2
  enable_multi_az         = true
  enable_global_datastore = true   # creates the Global Datastore group

  providers = { aws = aws.mumbai }
  tags      = local.common_tags
}

module "redis_hyderabad" {
  source      = "../../modules/redis"
  cluster_name = "prana-prod-dr"
  environment  = local.env
  vpc_id       = module.networking_hyderabad.vpc_id
  subnet_ids   = module.networking_hyderabad.private_subnet_ids

  allowed_security_group_ids = [
    module.networking_hyderabad.api_sg_id,
  ]

  node_type                   = "cache.r7g.xlarge"
  num_cache_clusters          = 2
  enable_multi_az             = true
  enable_global_datastore     = true
  global_replication_group_id = module.redis_mumbai.global_replication_group_id

  providers = { aws = aws.hyderabad }
  tags      = local.common_tags
}

# ── Compute — ECS (prana-api, prana-ai, prana-ask) ───────────────────────────

# ── YugabyteDB — dual-region active-active ────────────────────────────────────

module "yugabytedb" {
  source      = "../../modules/yugabytedb"
  environment = local.env
  vpc_id      = module.networking_mumbai.vpc_id
  subnet_ids  = module.networking_mumbai.private_subnet_ids

  allowed_sg_ids = [
    module.networking_mumbai.api_sg_id,
    module.networking_mumbai.ai_sg_id,
  ]

  node_count         = 3
  node_instance_type = "c5.4xlarge"   # 16 vCPU, 32 GB per node
  node_disk_gb       = 1000
  replication_factor = 3
  db_password        = var.yugabytedb_password

  regions = [
    { region = "ap-south-1", num_nodes = 3, az = "ap-south-1a" },
    { region = "ap-south-2", num_nodes = 3, az = "ap-south-2a" },
  ]

  enable_encryption_at_rest = true
  kms_config_id             = module.kms_platform_secret.key_id

  tags = local.common_tags
}

# ── Store DB connection string in Secrets Manager ─────────────────────────────

resource "aws_secretsmanager_secret" "db_url" {
  provider = aws.mumbai
  name     = "prana/prod/yugabytedb/connection-string"
  tags     = local.common_tags
}

resource "aws_secretsmanager_secret_version" "db_url" {
  provider      = aws.mumbai
  secret_id     = aws_secretsmanager_secret.db_url.id
  secret_string = module.yugabytedb.connection_string
}

# ── Kong API Gateway — ALB + Kong ECS ────────────────────────────────────────

module "kong_mumbai" {
  source      = "../../modules/kong"
  environment = local.env
  region      = "ap-south-1"

  vpc_id             = module.networking_mumbai.vpc_id
  private_subnet_ids = module.networking_mumbai.private_subnet_ids
  public_subnet_ids  = module.networking_mumbai.public_subnet_ids
  kong_sg_id         = module.networking_mumbai.kong_sg_id
  alb_sg_id          = module.networking_mumbai.alb_sg_id

  acm_certificate_arn   = var.acm_certificate_arn
  api_upstream_host     = "prana-api.${local.env}.internal"
  ask_upstream_host     = "prana-ask.${local.env}.internal"
  jwt_secret_arn        = aws_secretsmanager_secret.jwt_secret.arn
  kong_config_s3_bucket = module.s3_mumbai.documents_bucket
  kong_config_s3_key    = "config/kong.yml"
  execution_role_arn    = module.compute_mumbai.execution_role_arn

  kong_count = 3

  providers = { aws = aws.mumbai }
  tags      = local.common_tags
}

resource "aws_secretsmanager_secret" "jwt_secret" {
  provider = aws.mumbai
  name     = "prana/prod/jwt/signing-secret"
  tags     = local.common_tags
}

# ── Compute — ECS (prana-api, prana-ai, prana-ask) ───────────────────────────

module "compute_mumbai" {
  source      = "../../modules/compute"
  environment = local.env
  region      = "ap-south-1"
  vpc_id      = module.networking_mumbai.vpc_id
  subnet_ids  = module.networking_mumbai.private_subnet_ids

  api_sg_id = module.networking_mumbai.api_sg_id
  ai_sg_id  = module.networking_mumbai.ai_sg_id
  ask_sg_id = module.networking_mumbai.ask_sg_id

  api_image = var.api_image
  ai_image  = var.ai_image
  ask_image = var.ask_image

  api_count        = 3
  ai_count         = 2
  ask_count        = 1
  ai_instance_type = "g4dn.2xlarge"

  # IAM — wires policies to task roles
  kafka_cluster_arn       = module.kafka_mumbai.cluster_arn
  kafka_cluster_name      = "prana-prod"
  documents_bucket_arn    = module.s3_mumbai.documents_bucket_arn
  audit_cold_bucket_arn   = module.s3_mumbai.audit_cold_bucket_arn
  platform_secret_key_arn = module.kms_platform_secret.key_arn
  totp_key_arn            = module.kms_totp.key_arn
  aws_account_id          = data.aws_caller_identity.current.account_id
  aws_region              = "ap-south-1"

  # Env vars injected from Secrets Manager — app reads standard var names
  api_secrets = {
    KAFKA_BOOTSTRAP_SERVERS = aws_secretsmanager_secret.kafka_bootstrap.arn
    REDIS_URL               = module.redis_mumbai.auth_token_secret_arn
    PLATFORM_SECRET_KEY_ARN = module.kms_platform_secret.key_arn
    TOTP_KEY_ARN            = module.kms_totp.key_arn
    S3_DOCUMENTS_BUCKET     = aws_secretsmanager_secret.s3_bucket_name.arn
    DATABASE_URL            = aws_secretsmanager_secret.db_url.arn
  }

  ai_secrets = {
    KAFKA_BOOTSTRAP_SERVERS = aws_secretsmanager_secret.kafka_bootstrap.arn
    PLATFORM_SECRET_KEY_ARN = module.kms_platform_secret.key_arn
    S3_DOCUMENTS_BUCKET     = aws_secretsmanager_secret.s3_bucket_name.arn
    DATABASE_URL            = aws_secretsmanager_secret.db_url.arn
  }

  ask_secrets = {
    REDIS_URL    = module.redis_mumbai.auth_token_secret_arn
    DATABASE_URL = aws_secretsmanager_secret.db_url.arn
  }

  providers = { aws = aws.mumbai }
  tags      = local.common_tags
}

data "aws_caller_identity" "current" { provider = aws.mumbai }

# S3 bucket name secret (so app reads it from Secrets Manager same as other vars)
resource "aws_secretsmanager_secret" "s3_bucket_name" {
  provider = aws.mumbai
  name     = "prana/prod/s3/documents-bucket"
  tags     = local.common_tags
}
resource "aws_secretsmanager_secret_version" "s3_bucket_name" {
  provider      = aws.mumbai
  secret_id     = aws_secretsmanager_secret.s3_bucket_name.id
  secret_string = module.s3_mumbai.documents_bucket
}

# ── Route53 — api.<domain_name> → Kong ALB ───────────────────────────────────

locals {
  api_fqdn = "${var.api_subdomain}.${var.domain_name}"
}

resource "aws_route53_record" "api" {
  provider = aws.mumbai
  zone_id  = var.route53_zone_id
  name     = local.api_fqdn
  type     = "A"

  alias {
    name                   = module.kong_mumbai.alb_dns_name
    zone_id                = module.kong_mumbai.alb_zone_id
    evaluate_target_health = true
  }
}

output "api_url" { value = "https://${local.api_fqdn}" }

# ── Kafka bootstrap secret (consumed by compute module) ───────────────────────

resource "aws_secretsmanager_secret" "kafka_bootstrap" {
  provider = aws.mumbai
  name     = "prana/prod/kafka/bootstrap-servers"
  tags     = local.common_tags
}

resource "aws_secretsmanager_secret_version" "kafka_bootstrap" {
  provider      = aws.mumbai
  secret_id     = aws_secretsmanager_secret.kafka_bootstrap.id
  secret_string = module.kafka_mumbai.bootstrap_servers
}
