# ── Compute module — ECS tasks for 3 PRANA services ──────────────────────────
# DEPLOYMENT BOUNDARY ENFORCED:
#   - prana-api  → Fargate (CPU), separate task role, no GPU
#   - prana-ai   → EC2 (GPU g4dn), separate task role, no API access
#   - prana-ask  → EC2 (GPU g4dn), separate task role, no API access
# Cross-service isolation: task roles have least-privilege IAM —
# prana-ai cannot read JWT secrets; prana-ask cannot write to Kafka topics

locals {
  name = "prana-${var.environment}"
}

resource "aws_ecs_cluster" "prana" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = var.tags
}

# ── prana-api — Fargate (CPU) ─────────────────────────────────────────────────

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.api_execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  container_definitions = jsonencode([{
    name      = "prana-api"
    image     = var.api_image
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]

    secrets = [for k, v in var.api_secrets : { name = k, valueFrom = v }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/prana/${var.environment}/api"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])

  tags = var.tags
}

resource "aws_ecs_service" "api" {
  name            = "${local.name}-api"
  cluster         = aws_ecs_cluster.prana.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.subnet_ids
    security_groups = [var.api_sg_id]
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = var.tags
}

# ── prana-ai — EC2 GPU ────────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "ai" {
  family             = "${local.name}-ai"
  network_mode       = "awsvpc"
  execution_role_arn = aws_iam_role.ai_execution.arn
  task_role_arn      = aws_iam_role.ai_task.arn

  # GPU requires EC2 launch type with resourceRequirements
  container_definitions = jsonencode([{
    name      = "prana-ai"
    image     = var.ai_image
    essential = true

    resourceRequirements = [{ type = "GPU", value = "1" }]

    secrets = [for k, v in var.ai_secrets : { name = k, valueFrom = v }]

    # VPC-internal URL for prana-ai → prana-api callbacks (bypasses Kong — authorised bypass).
    # Never use the public Kong/ALB URL from prana-ai — INTERNAL-01 in enforce_rules.py catches this.
    environment = [
      {
        name  = "PRANA_API_INTERNAL_URL"
        value = "http://prana-api.${var.environment}.internal:8000"
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/prana/${var.environment}/ai"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "ai"
      }
    }
  }])

  tags = var.tags
}

resource "aws_ecs_service" "ai" {
  name            = "${local.name}-ai"
  cluster         = aws_ecs_cluster.prana.id
  task_definition = aws_ecs_task_definition.ai.arn
  desired_count   = var.ai_count
  launch_type     = "EC2"

  network_configuration {
    subnets         = var.subnet_ids
    security_groups = [var.ai_sg_id]
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = var.tags
}

# ── prana-ask — EC2 GPU ───────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "ask" {
  family             = "${local.name}-ask"
  network_mode       = "awsvpc"
  execution_role_arn = aws_iam_role.ask_execution.arn
  task_role_arn      = aws_iam_role.ask_task.arn

  container_definitions = jsonencode([{
    name      = "prana-ask"
    image     = var.ask_image
    essential = true

    resourceRequirements = [{ type = "GPU", value = "1" }]

    secrets = [for k, v in var.ask_secrets : { name = k, valueFrom = v }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/prana/${var.environment}/ask"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "ask"
      }
    }
  }])

  tags = var.tags
}

resource "aws_ecs_service" "ask" {
  name            = "${local.name}-ask"
  cluster         = aws_ecs_cluster.prana.id
  task_definition = aws_ecs_task_definition.ask.arn
  desired_count   = var.ask_count
  launch_type     = "EC2"

  network_configuration {
    subnets         = var.subnet_ids
    security_groups = [var.ask_sg_id]
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = var.tags
}

# ── IAM task roles (least-privilege) ─────────────────────────────────────────

resource "aws_iam_role" "api_task" {
  name = "${local.name}-api-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  tags = var.tags
}

resource "aws_iam_role" "ai_task" {
  name = "${local.name}-ai-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  # prana-ai: can read S3 docs, call KMS decrypt, write to Textract — nothing else
  tags = var.tags
}

resource "aws_iam_role" "ask_task" {
  name = "${local.name}-ask-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  # prana-ask: can read Qdrant, call KMS decrypt — cannot write Kafka or DB
  tags = var.tags
}

resource "aws_iam_role" "api_execution"  { name = "${local.name}-api-exec-role";  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json; tags = var.tags }
resource "aws_iam_role" "ai_execution"   { name = "${local.name}-ai-exec-role";   assume_role_policy = data.aws_iam_policy_document.ecs_assume.json; tags = var.tags }
resource "aws_iam_role" "ask_execution"  { name = "${local.name}-ask-exec-role";  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json; tags = var.tags }

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals { type = "Service"; identifiers = ["ecs-tasks.amazonaws.com"] }
  }
}

resource "aws_iam_role_policy_attachment" "exec_policy" {
  for_each   = { api = aws_iam_role.api_execution.name, ai = aws_iam_role.ai_execution.name, ask = aws_iam_role.ask_execution.name }
  role       = each.value
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

output "cluster_id"           { value = aws_ecs_cluster.prana.id }
output "ecs_cluster_id"      { value = aws_ecs_cluster.prana.id }
output "api_task_role_arn"   { value = aws_iam_role.api_task.arn }
output "ai_task_role_arn"    { value = aws_iam_role.ai_task.arn }
output "ask_task_role_arn"   { value = aws_iam_role.ask_task.arn }
output "execution_role_arn"  { value = aws_iam_role.api_execution.arn }
