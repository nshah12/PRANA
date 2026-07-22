# ── Networking module — VPC, subnets, SGs ────────────────────────────────────

variable "environment"  { type = string }
variable "region"       { type = string }
variable "vpc_cidr"     { type = string; default = "10.0.0.0/16" }
variable "tags"         { type = map(string); default = {} }

locals {
  name = "prana-${var.environment}"
  # 2 AZs per region: a and b
  azs             = ["${var.region}a", "${var.region}b"]
  private_cidrs   = ["10.0.1.0/24", "10.0.2.0/24"]
  public_cidrs    = ["10.0.101.0/24", "10.0.102.0/24"]
}

resource "aws_vpc" "prana" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = merge(var.tags, { Name = "${local.name}-vpc" })
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.prana.id
  cidr_block        = local.private_cidrs[count.index]
  availability_zone = local.azs[count.index]
  tags              = merge(var.tags, { Name = "${local.name}-private-${local.azs[count.index]}", Tier = "private" })
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.prana.id
  cidr_block              = local.public_cidrs[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = false
  tags                    = merge(var.tags, { Name = "${local.name}-public-${local.azs[count.index]}", Tier = "public" })
}

resource "aws_internet_gateway" "prana" {
  vpc_id = aws_vpc.prana.id
  tags   = merge(var.tags, { Name = "${local.name}-igw" })
}

resource "aws_eip" "nat" {
  count  = 2
  domain = "vpc"
  tags   = merge(var.tags, { Name = "${local.name}-nat-eip-${count.index}" })
}

resource "aws_nat_gateway" "prana" {
  count         = 2
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  tags          = merge(var.tags, { Name = "${local.name}-nat-${count.index}" })
}

resource "aws_route_table" "private" {
  count  = 2
  vpc_id = aws_vpc.prana.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.prana[count.index].id
  }
  tags = merge(var.tags, { Name = "${local.name}-private-rt-${count.index}" })
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# ── Security groups ───────────────────────────────────────────────────────────

resource "aws_security_group" "api" {
  name        = "${local.name}-api-sg"
  description = "prana-api service — ingress from Kong SG only (see aws_security_group_rule.api_from_kong)"
  vpc_id      = aws_vpc.prana.id

  # No ingress rules here — added via aws_security_group_rule.api_from_kong below.
  # This ensures prana-api is reachable ONLY from Kong, not from the broad VPC CIDR.

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name}-api-sg" })
}

resource "aws_security_group" "ai" {
  name        = "${local.name}-ai-sg"
  description = "prana-ai GPU worker"
  vpc_id      = aws_vpc.prana.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name}-ai-sg" })
}

resource "aws_security_group" "ask" {
  name        = "${local.name}-ask-sg"
  description = "prana-ask GPU worker"
  vpc_id      = aws_vpc.prana.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name}-ask-sg" })
}

# Kong API gateway — receives traffic from the public ALB
resource "aws_security_group" "kong" {
  name        = "${local.name}-kong-sg"
  description = "Kong API gateway"
  vpc_id      = aws_vpc.prana.id

  ingress {
    description = "HTTPS proxy port from ALB"
    from_port   = 8443
    to_port     = 8443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  ingress {
    description = "Admin API — internal only (no ALB listener)"
    from_port   = 8001
    to_port     = 8001
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name}-kong-sg" })
}

# ALB — public-facing, terminates TLS, forwards to Kong
resource "aws_security_group" "alb" {
  name        = "${local.name}-alb-sg"
  description = "Public ALB in front of Kong"
  vpc_id      = aws_vpc.prana.id

  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP redirect to HTTPS"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name}-alb-sg" })
}

# Allow API SG to receive from Kong only (external traffic path)
resource "aws_security_group_rule" "api_from_kong" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.api.id
  source_security_group_id = aws_security_group.kong.id
  description              = "prana-api reachable from Kong (external callers)"
}

# Allow prana-ai to call prana-api DIRECTLY — VPC-internal, bypasses Kong intentionally.
# This is the ONLY authorised bypass. prana-ai never calls the public ALB.
# Rule: INTERNAL-01 in enforce_rules.py catches code violations of this boundary.
resource "aws_security_group_rule" "api_from_ai_internal" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.api.id
  source_security_group_id = aws_security_group.ai.id
  description              = "prana-ai pipeline callbacks to prana-api — VPC-internal only, no Kong"
}

# Allow ask SG to receive from Kong only
resource "aws_security_group_rule" "ask_from_kong" {
  type                     = "ingress"
  from_port                = 8080
  to_port                  = 8080
  protocol                 = "tcp"
  security_group_id        = aws_security_group.ask.id
  source_security_group_id = aws_security_group.kong.id
  description              = "prana-ask only reachable from Kong"
}

# ── Temporal SG — gRPC port 7233 open to prana-api only ──────────────────────
resource "aws_security_group" "temporal" {
  name        = "${local.name}-temporal"
  description = "Temporal server — prana-api connects on 7233"
  vpc_id      = aws_vpc.prana.id
  tags        = merge(var.tags, { Name = "${local.name}-temporal" })
}

resource "aws_security_group_rule" "temporal_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.temporal.id
}

output "vpc_id"              { value = aws_vpc.prana.id }
output "private_subnet_ids"  { value = aws_subnet.private[*].id }
output "public_subnet_ids"   { value = aws_subnet.public[*].id }
output "api_sg_id"           { value = aws_security_group.api.id }
output "ai_sg_id"            { value = aws_security_group.ai.id }
output "ask_sg_id"           { value = aws_security_group.ask.id }
output "kong_sg_id"          { value = aws_security_group.kong.id }
output "alb_sg_id"           { value = aws_security_group.alb.id }
output "temporal_sg_id"      { value = aws_security_group.temporal.id }
