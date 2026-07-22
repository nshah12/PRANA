# ── YugabyteDB module — cloud-agnostic ───────────────────────────────────────
# YugabyteDB runs identically on AWS, Azure, GCP, or bare metal.
# This module provisions a YugabyteDB Anywhere (YBA) managed cluster.
# Already cloud-agnostic — NO swap needed when moving to Azure.
#
# Alternatives (all use same PostgreSQL wire protocol, zero app code change):
#   - YugabyteDB Managed (fully managed SaaS)
#   - Self-hosted on EC2/AKS/GKE
#   - YugabyteDB Anywhere (on-prem control plane)

variable "environment"        { type = string }
variable "cluster_name"       { type = string; default = "prana" }
variable "vpc_id"             { type = string }
variable "subnet_ids"         { type = list(string) }
variable "allowed_sg_ids"     { type = list(string) }

variable "node_count" {
  type    = number
  default = 3   # prod: 3 nodes minimum for RF=3
}

variable "node_instance_type" {
  type    = string
  default = "c5.2xlarge"
  # 8 vCPU, 16 GB RAM per node — handles 1 crore employee rows
}

variable "node_disk_gb" {
  type    = number
  default = 500
}

variable "replication_factor" {
  type    = number
  default = 3
}

variable "regions" {
  type = list(object({
    region      = string
    num_nodes   = number
    az          = string
  }))
  default = [
    { region = "ap-south-1", num_nodes = 3, az = "ap-south-1a" },
    { region = "ap-south-2", num_nodes = 3, az = "ap-south-2a" },
  ]
}

variable "enable_encryption_at_rest" { type = bool; default = true }
variable "kms_config_id"             { type = string; default = "" }
variable "tags"                      { type = map(string); default = {} }

# ── Security group ────────────────────────────────────────────────────────────

resource "aws_security_group" "yugabytedb" {
  name        = "prana-${var.environment}-yugabytedb-sg"
  description = "YugabyteDB node access"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL wire protocol"
    from_port       = 5433
    to_port         = 5433
    protocol        = "tcp"
    security_groups = var.allowed_sg_ids
  }

  ingress {
    description = "YugabyteDB inter-node RPC"
    from_port   = 7100
    to_port     = 7100
    protocol    = "tcp"
    self        = true
  }

  ingress {
    description = "YugabyteDB inter-node tablet server"
    from_port   = 9100
    to_port     = 9100
    protocol    = "tcp"
    self        = true
  }

  ingress {
    description = "YugabyteDB UI (internal only)"
    from_port   = 7000
    to_port     = 7000
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "prana-${var.environment}-yugabytedb-sg" })
}

# ── YugabyteDB cluster (via YBA Terraform provider) ──────────────────────────
# Provider: registry.terraform.io/yugabyte/yugabyte
# Same provider config works on AWS, Azure, GCP — just change cloud_info block.

resource "yugabyte_cluster" "prana" {
  cluster_info = {
    name              = "prana-${var.environment}"
    num_nodes         = var.node_count
    replication_factor = var.replication_factor
    node_config = {
      num_cores    = 8
      disk_size_gb = var.node_disk_gb
      memory_mb    = 16384
    }
  }

  # SWAP CONTRACT: change cloud_type + region_info for Azure/GCP.
  # cluster_info, software_version, communication_ports stay identical.
  cloud_info = {
    code = "AWS"   # "AZURE" | "GCP" | "ON_PREM" — only this line changes for cloud swap
    region = {
      code = var.regions[0].region
      zones = [{ name = var.regions[0].az, num_nodes = var.regions[0].num_nodes }]
    }
  }

  software_info = {
    yb_version = "2.20.2.0"
  }

  communication_ports = {
    master_http_port      = 7000
    master_rpc_port       = 7100
    tserver_http_port     = 9000
    tserver_rpc_port      = 9100
    yql_server_http_port  = 12000
    yql_server_rpc_port   = 9042
    ysql_server_http_port = 13000
    ysql_server_rpc_port  = 5433
  }
}

# ── DB init: apply schema + RLS + migrations ──────────────────────────────────
# Runs prana-db/schema.sql after cluster is ready.
# null_resource + local-exec so this works on any cloud.

resource "null_resource" "schema_apply" {
  depends_on = [yugabyte_cluster.prana]

  triggers = {
    schema_hash = filemd5("${path.root}/../../../prana-db/schema.sql")
    cluster_id  = yugabyte_cluster.prana.cluster_id
  }

  provisioner "local-exec" {
    command = <<-EOT
      PGPASSWORD=$DB_PASSWORD psql \
        -h ${yugabyte_cluster.prana.cluster_endpoint} \
        -p 5433 \
        -U yugabyte \
        -d prana \
        -f ${path.root}/../../../prana-db/schema.sql
    EOT
    environment = {
      DB_PASSWORD = var.db_password
    }
  }
}

variable "db_password" {
  type      = string
  sensitive = true
}

output "connection_string" {
  description = "PostgreSQL connection string — maps to DATABASE_URL env var"
  value       = "postgresql://yugabyte:${var.db_password}@${yugabyte_cluster.prana.cluster_endpoint}:5433/prana"
  sensitive   = true
}

output "cluster_endpoint" {
  value = yugabyte_cluster.prana.cluster_endpoint
}

output "security_group_id" {
  value = aws_security_group.yugabytedb.id
}

output "cluster_id" {
  value = yugabyte_cluster.prana.cluster_id
}
