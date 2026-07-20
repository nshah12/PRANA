# ── Temporal module — self-hosted on ECS Fargate ──────────────────────────────
# Persistence: YugabyteDB (PostgreSQL-compatible) — same cluster as prana-api
# Visibility: DB visibility (no Elasticsearch needed at this scale)
# Ports: 7233 (frontend gRPC), 7234 (history), 7235 (matching), 7239 (UI)
#
# Temporal Cloud alternative: replace this entire module with a Temporal Cloud
# namespace and update TEMPORAL_HOST_URL in prana-api secrets. Zero code change.

locals {
  name = "prana-${var.environment}-temporal"
}

# ── CloudWatch log groups ──────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "temporal_server" {
  name              = "/prana/${var.environment}/temporal/server"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "temporal_ui" {
  name              = "/prana/${var.environment}/temporal/ui"
  retention_in_days = 14
  tags              = var.tags
}

# ── Security group — Temporal frontend (7233) ─────────────────────────────────

resource "aws_security_group_rule" "allow_api_to_temporal" {
  type                     = "ingress"
  from_port                = 7233
  to_port                  = 7233
  protocol                 = "tcp"
  security_group_id        = var.temporal_sg_id
  source_security_group_id = var.api_sg_id
  description              = "prana-api → Temporal frontend gRPC"
}

resource "aws_security_group_rule" "temporal_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = var.temporal_sg_id
}

# ── IAM task role ─────────────────────────────────────────────────────────────

resource "aws_iam_role" "temporal_task" {
  name = "${local.name}-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "temporal_secrets" {
  name = "read-db-secret"
  role = aws_iam_role.temporal_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [var.db_url_secret_arn]
    }]
  })
}

# ── ECS Task Definition — Temporal server ─────────────────────────────────────

resource "aws_ecs_task_definition" "temporal_server" {
  family                   = "${local.name}-server"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.server_cpu
  memory                   = var.server_memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = aws_iam_role.temporal_task.arn

  container_definitions = jsonencode([{
    name      = "temporal-server"
    image     = var.temporal_image
    essential = true

    portMappings = [
      { containerPort = 7233, protocol = "tcp" },  # frontend gRPC (workers + API connect here)
      { containerPort = 7234, protocol = "tcp" },  # history
      { containerPort = 7235, protocol = "tcp" },  # matching
      { containerPort = 7236, protocol = "tcp" },  # worker
    ]

    environment = [
      { name = "DB",                       value = "postgres12" },
      { name = "DB_PORT",                  value = "5433" },
      { name = "TEMPORAL_ADDRESS",         value = "0.0.0.0:7233" },
      { name = "BIND_ON_IP",               value = "0.0.0.0" },
      { name = "NUM_HISTORY_SHARDS",       value = "512" },
      { name = "LOG_LEVEL",                value = "info" },
      { name = "TEMPORAL_VISIBILITY_STORE", value = "postgres12" },
    ]

    secrets = [
      { name = "POSTGRES_SEEDS", valueFrom = var.db_url_secret_arn },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.temporal_server.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "temporal"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "temporal-diagnostic --serverAddress 127.0.0.1:7233 || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 5
      startPeriod = 120  # auto-setup runs schema migration on first boot
    }
  }])

  tags = var.tags
}

# ── ECS Service — Temporal server ─────────────────────────────────────────────

resource "aws_ecs_service" "temporal_server" {
  name                               = "${local.name}-server"
  cluster                            = var.ecs_cluster_id
  task_definition                    = aws_ecs_task_definition.temporal_server.arn
  desired_count                      = var.server_count
  launch_type                        = "FARGATE"
  health_check_grace_period_seconds  = 180

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [var.temporal_sg_id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.temporal.arn
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = var.tags
}

# ── Service Discovery — prana-api connects via temporal.prana.local:7233 ──────

resource "aws_service_discovery_private_dns_namespace" "prana" {
  name        = "prana.local"
  description = "PRANA internal service discovery"
  vpc         = var.vpc_id
  tags        = var.tags
}

resource "aws_service_discovery_service" "temporal" {
  name = "temporal"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.prana.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# ── ECS Task Definition — Temporal UI ─────────────────────────────────────────

resource "aws_ecs_task_definition" "temporal_ui" {
  family                   = "${local.name}-ui"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ui_cpu
  memory                   = var.ui_memory
  execution_role_arn       = var.execution_role_arn

  container_definitions = jsonencode([{
    name      = "temporal-ui"
    image     = var.temporal_ui_image
    essential = true

    portMappings = [{ containerPort = 8080, protocol = "tcp" }]

    environment = [
      { name = "TEMPORAL_ADDRESS",         value = "temporal.prana.local:7233" },
      { name = "TEMPORAL_CORS_ORIGINS",    value = "http://localhost:8088" },
      { name = "TEMPORAL_UI_PORT",         value = "8080" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.temporal_ui.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "temporal-ui"
      }
    }
  }])

  tags = var.tags
}

resource "aws_ecs_service" "temporal_ui" {
  name            = "${local.name}-ui"
  cluster         = var.ecs_cluster_id
  task_definition = aws_ecs_task_definition.temporal_ui.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [var.temporal_sg_id]
    assign_public_ip = false
  }

  tags = var.tags
}
