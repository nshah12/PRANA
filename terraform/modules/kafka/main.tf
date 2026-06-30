# ── Kafka module — AWS MSK backend ───────────────────────────────────────────
# TO SWAP TO CONFLUENT CLOUD:
#   1. Replace this file with confluent_kafka_cluster resource blocks
#   2. Keep variables.tf and outputs.tf identical
#   3. No changes needed in environments/ or in application code
#
# The outputs (bootstrap_servers, security_group_id) are the swap contract.

locals {
  name = "prana-${var.environment}-kafka"
  az_count = length(var.subnet_ids)
  broker_count = var.broker_count_per_az * local.az_count
}

# ── Security group ────────────────────────────────────────────────────────────

resource "aws_security_group" "kafka" {
  name        = "${local.name}-sg"
  description = "PRANA Kafka broker access"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Kafka plaintext (internal only)"
    from_port       = 9092
    to_port         = 9092
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
  }

  ingress {
    description     = "Kafka TLS"
    from_port       = 9094
    to_port         = 9094
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

# ── MSK cluster ───────────────────────────────────────────────────────────────

resource "aws_msk_cluster" "prana" {
  cluster_name           = local.name
  kafka_version          = var.kafka_version
  number_of_broker_nodes = local.broker_count

  broker_node_group_info {
    instance_type   = var.broker_instance_type
    client_subnets  = var.subnet_ids
    security_groups = [aws_security_group.kafka.id]

    storage_info {
      ebs_storage_info {
        volume_size = var.broker_storage_gb
      }
    }
  }

  # KRaft mode — no ZooKeeper
  broker_node_group_info {
    instance_type   = var.broker_instance_type
    client_subnets  = var.subnet_ids
    security_groups = [aws_security_group.kafka.id]

    storage_info {
      ebs_storage_info { volume_size = var.broker_storage_gb }
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  client_authentication {
    sasl { iam = true }
  }

  configuration_info {
    arn      = aws_msk_configuration.prana.arn
    revision = aws_msk_configuration.prana.latest_revision
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = "/prana/${var.environment}/kafka/broker"
      }
    }
  }

  tags = merge(var.tags, { Name = local.name })
}

# ── Cluster configuration ─────────────────────────────────────────────────────

resource "aws_msk_configuration" "prana" {
  name              = "${local.name}-config"
  kafka_versions    = [var.kafka_version]
  server_properties = <<-EOT
    auto.create.topics.enable=false
    default.replication.factor=2
    min.insync.replicas=1
    num.partitions=12
    log.retention.hours=168
    log.segment.bytes=1073741824
    offsets.topic.replication.factor=3
    transaction.state.log.replication.factor=3
    transaction.state.log.min.isr=2
  EOT
}

# ── Topics (via Kafka provider) ───────────────────────────────────────────────
# Uses the community kafka provider (registry.terraform.io/Mongey/kafka)
# Same provider works against Confluent Cloud — just change bootstrap_servers

resource "kafka_topic" "topics" {
  for_each = var.topics

  name               = each.key
  replication_factor = each.value.replication
  partitions         = each.value.partitions

  config = {
    "retention.ms"    = tostring(each.value.retention_hours * 3600 * 1000)
    "cleanup.policy"  = "delete"
    "compression.type" = "lz4"
  }
}

# ── MirrorMaker 2 (prod only) ─────────────────────────────────────────────────

resource "aws_msk_replicator" "mm2" {
  count = var.enable_mirrormaker ? 1 : 0

  replicator_name = "${local.name}-mm2"

  kafka_cluster {
    amazon_msk_cluster {
      msk_cluster_arn = aws_msk_cluster.prana.arn
    }
    vpc_config {
      subnet_ids         = var.subnet_ids
      security_groups_ids = [aws_security_group.kafka.id]
    }
  }

  kafka_cluster {
    amazon_msk_cluster {
      msk_cluster_arn = var.mirrormaker_source_bootstrap_servers
    }
    vpc_config {
      subnet_ids          = var.subnet_ids
      security_groups_ids = [aws_security_group.kafka.id]
    }
  }

  replication_info_list {
    source_kafka_cluster_arn = var.mirrormaker_source_bootstrap_servers
    target_kafka_cluster_arn = aws_msk_cluster.prana.arn
    target_compression_type  = "LZ4"

    topic_replication {
      topics_to_replicate = ["prana.*"]
    }

    consumer_group_replication {
      consumer_groups_to_replicate = ["prana-*"]
    }
  }

  service_execution_role_arn = aws_iam_role.mm2[0].arn
}

resource "aws_iam_role" "mm2" {
  count = var.enable_mirrormaker ? 1 : 0
  name  = "${local.name}-mm2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "kafkaconnect.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}
