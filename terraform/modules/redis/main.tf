# ── Redis module — AWS ElastiCache backend ────────────────────────────────────
# TO SWAP TO REDIS ENTERPRISE CLOUD:
#   Replace resource blocks below with rediscloud_subscription +
#   rediscloud_database. Keep variables.tf and outputs.tf identical.

locals {
  name = "prana-${var.environment}-redis"
}

resource "aws_security_group" "redis" {
  name        = "${local.name}-sg"
  description = "PRANA Redis access"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name}-sg" })
}

resource "aws_elasticache_subnet_group" "prana" {
  name       = "${local.name}-subnet-group"
  subnet_ids = var.subnet_ids
}

resource "aws_elasticache_replication_group" "prana" {
  replication_group_id = local.name
  description          = "PRANA Redis — 4 namespaces: identity, share tokens, vault health, JWT revocation"

  node_type            = var.node_type
  num_cache_clusters   = var.num_cache_clusters
  port                 = 6379

  subnet_group_name    = aws_elasticache_subnet_group.prana.name
  security_group_ids   = [aws_security_group.redis.id]

  at_rest_encryption_enabled  = true
  transit_encryption_enabled  = true
  auth_token                  = random_password.redis_auth.result

  automatic_failover_enabled  = var.enable_multi_az
  multi_az_enabled            = var.enable_multi_az

  # Pub/Sub for SSE fanout — needs keyspace notifications enabled
  parameter_group_name = aws_elasticache_parameter_group.prana.name

  log_delivery_configuration {
    destination      = "/prana/${var.environment}/redis/slow"
    destination_type = "cloudwatch-logs"
    log_format       = "json"
    log_type         = "slow-log"
  }

  tags = merge(var.tags, { Name = local.name })
}

resource "aws_elasticache_parameter_group" "prana" {
  name   = "${local.name}-params"
  family = "redis7"

  # Enable keyspace notifications for SSE Pub/Sub pattern
  parameter {
    name  = "notify-keyspace-events"
    value = "KEA"
  }

  # CRDT-compatible settings
  parameter {
    name  = "maxmemory-policy"
    value = "volatile-lru"
  }
}

resource "random_password" "redis_auth" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "redis_auth" {
  name = "prana/${var.environment}/redis/auth-token"
  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "redis_auth" {
  secret_id     = aws_secretsmanager_secret.redis_auth.id
  secret_string = random_password.redis_auth.result
}

# ── Global Datastore (prod only) ──────────────────────────────────────────────
# Links ap-south-1 (primary) and ap-south-2 (secondary) clusters
# CRDT active-active: both regions can write, sub-10ms sync

resource "aws_elasticache_global_replication_group" "prana" {
  count = var.enable_global_datastore && var.global_replication_group_id == "" ? 1 : 0

  global_replication_group_id_suffix = "prana-${var.environment}"
  primary_replication_group_id       = aws_elasticache_replication_group.prana.id
  automatic_failover_enabled         = true
}
