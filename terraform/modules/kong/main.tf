# ── Kong API Gateway — ECS Fargate, DB-less declarative mode ─────────────────
#
# Traffic flow:
#   Internet → ALB (TLS termination) → Kong ECS (port 8443) → prana-api / prana-ask
#
# Kong runs in DB-less mode: config loaded from kong.yml on S3 at startup.
# No Kong database needed — config changes deploy as new ECS task revisions.
# Admin API (port 8001) is NEVER exposed via ALB — internal VPC only.

locals {
  name = "prana-${var.environment}-kong"
}

# ── IAM task role for Kong ────────────────────────────────────────────────────

resource "aws_iam_role" "kong_task" {
  name = "${local.name}-task-role"
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

resource "aws_iam_role_policy" "kong_task" {
  name = "${local.name}-task-policy"
  role = aws_iam_role.kong_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Kong reads its declarative config from S3 at startup
        Sid      = "ReadKongConfig"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:aws:s3:::${var.kong_config_s3_bucket}/${var.kong_config_s3_key}"
      },
      {
        # Read JWT signing secret for jwt plugin validation
        Sid      = "ReadJwtSecret"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.jwt_secret_arn
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.kong.arn}:*"
      }
    ]
  })
}

# ── CloudWatch log group ──────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "kong" {
  name              = "/ecs/prana-${var.environment}/kong"
  retention_in_days = 30
  tags              = var.tags
}

# ── ECS cluster (shared with compute module in prod — separate here for clarity)

resource "aws_ecs_cluster" "kong" {
  name = "${local.name}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  tags = var.tags
}

# ── ECS Task Definition ───────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "kong" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.kong_cpu
  memory                   = var.kong_memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = aws_iam_role.kong_task.arn

  container_definitions = jsonencode([{
    name  = "kong"
    image = var.kong_image

    portMappings = [
      { containerPort = 8443, protocol = "tcp", name = "proxy-tls" },
      { containerPort = 8000, protocol = "tcp", name = "proxy-plain" },
      { containerPort = 8001, protocol = "tcp", name = "admin" }
    ]

    environment = [
      # DB-less mode — config loaded from file
      { name = "KONG_DATABASE",      value = "off" },
      { name = "KONG_DECLARATIVE_CONFIG", value = "/kong/kong.yml" },

      # Proxy listeners
      { name = "KONG_PROXY_LISTEN",  value = "0.0.0.0:8000, 0.0.0.0:8443 ssl" },
      # Admin API — bound to localhost inside container only (not exposed via ALB)
      { name = "KONG_ADMIN_LISTEN",  value = "127.0.0.1:8001" },

      # SSL cert — Kong will use ACM cert via ALB; plain on 8000 for VPC-internal probes
      { name = "KONG_SSL",           value = "off" },   # TLS terminated at ALB

      # Logging
      { name = "KONG_LOG_LEVEL",     value = "warn" },
      { name = "KONG_PROXY_ACCESS_LOG", value = "/dev/stdout" },
      { name = "KONG_PROXY_ERROR_LOG",  value = "/dev/stderr" },
    ]

    # Startup command: fetch kong.yml from S3, then start Kong
    command = [
      "/bin/sh", "-c",
      "aws s3 cp s3://${var.kong_config_s3_bucket}/${var.kong_config_s3_key} /kong/kong.yml && kong start"
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.kong.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "kong"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
      interval    = 15
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])

  tags = var.tags
}

# ── ECS Service ───────────────────────────────────────────────────────────────

resource "aws_ecs_service" "kong" {
  name            = local.name
  cluster         = aws_ecs_cluster.kong.id
  task_definition = aws_ecs_task_definition.kong.arn
  desired_count   = var.kong_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.kong_sg_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.kong.arn
    container_name   = "kong"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.https]

  tags = var.tags
}

# ── ALB ───────────────────────────────────────────────────────────────────────

resource "aws_lb" "kong" {
  name               = "${local.name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_sg_id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.environment == "prod"

  access_logs {
    bucket  = var.kong_config_s3_bucket
    prefix  = "alb-logs"
    enabled = true
  }

  tags = var.tags
}

resource "aws_lb_target_group" "kong" {
  name        = "${local.name}-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
    matcher             = "200"
  }

  tags = var.tags
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.kong.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.kong.arn
  }
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.kong.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# ── Auto-scaling ──────────────────────────────────────────────────────────────

resource "aws_appautoscaling_target" "kong" {
  max_capacity       = var.kong_count * 4
  min_capacity       = var.kong_count
  resource_id        = "service/${aws_ecs_cluster.kong.name}/${aws_ecs_service.kong.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "kong_cpu" {
  name               = "${local.name}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.kong.resource_id
  scalable_dimension = aws_appautoscaling_target.kong.scalable_dimension
  service_namespace  = aws_appautoscaling_target.kong.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = 60.0
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    scale_in_cooldown  = 60
    scale_out_cooldown = 30
  }
}
