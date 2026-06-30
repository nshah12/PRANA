# ── Kafka module variables ────────────────────────────────────────────────────
# Abstraction contract: callers pass these regardless of whether the backend
# is AWS MSK, Confluent Cloud, or Azure Event Hubs.
# To swap provider: change main.tf in this module only. Outputs stay identical.

variable "cluster_name" {
  type        = string
  description = "Logical name — becomes part of the MSK cluster name"
}

variable "environment" {
  type        = string
  description = "dev | staging | prod"
}

variable "vpc_id" {
  type        = string
  description = "VPC where broker ENIs are placed"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnets — one per AZ, 2 AZs minimum for prod"
}

variable "allowed_security_group_ids" {
  type        = list(string)
  description = "SGs allowed to connect to brokers (prana-api, prana-ai)"
}

variable "kafka_version" {
  type    = string
  default = "3.6.0"
}

variable "broker_instance_type" {
  type    = string
  default = "kafka.m5.large"
  # prod: kafka.m5.2xlarge
  # dev:  kafka.t3.small
}

variable "broker_count_per_az" {
  type    = number
  default = 1
  # prod: 3 brokers × 2 AZs = 6 total
}

variable "broker_storage_gb" {
  type    = number
  default = 1000
}

# ── Topics ────────────────────────────────────────────────────────────────────
# All 21 PRANA topics defined here as a map so adding a topic is one line.
# partition_count and retention_hours per topic.

variable "topics" {
  type = map(object({
    partitions       = number
    replication      = number
    retention_hours  = number
  }))
  default = {
    "prana.ingest.events"             = { partitions = 12, replication = 2, retention_hours = 168  }
    "prana.pipeline.events"           = { partitions = 12, replication = 2, retention_hours = 72   }
    "prana.vault.events"              = { partitions = 12, replication = 2, retention_hours = 168  }
    "prana.employee.events"           = { partitions = 12, replication = 2, retention_hours = 168  }
    "prana.tenant.events"             = { partitions = 12, replication = 2, retention_hours = 168  }
    "prana.oa_users.events"           = { partitions = 12, replication = 2, retention_hours = 168  }
    "prana.compliance.events"         = { partitions = 12, replication = 2, retention_hours = 720  }
    "prana.auth.events"               = { partitions = 12, replication = 2, retention_hours = 168  }
    "prana.security.events"           = { partitions = 24, replication = 3, retention_hours = 2160 }
    "prana.statutory.events"          = { partitions = 12, replication = 2, retention_hours = 720  }
    "prana.analytics.events"          = { partitions = 24, replication = 2, retention_hours = 168  }
    "prana.integrations.events"       = { partitions = 12, replication = 2, retention_hours = 168  }
    "prana.platform.events"           = { partitions = 12, replication = 2, retention_hours = 168  }
    "prana.audit.events"              = { partitions = 48, replication = 3, retention_hours = 87600 } # 10 years
    "prana.notifications.email"       = { partitions = 12, replication = 2, retention_hours = 48   }
    "prana.notifications.sms"         = { partitions = 12, replication = 2, retention_hours = 48   }
    "prana.notifications.push"        = { partitions = 12, replication = 2, retention_hours = 48   }
    "prana.notifications.whatsapp"    = { partitions = 12, replication = 2, retention_hours = 48   }
    "prana.notifications.portal_bell" = { partitions = 12, replication = 2, retention_hours = 168  }
  }
}

variable "enable_mirrormaker" {
  type    = bool
  default = false
  # Set true in prod to enable MirrorMaker 2 bidirectional sync
}

variable "mirrormaker_source_bootstrap_servers" {
  type    = string
  default = ""
  # Bootstrap servers of the peer region cluster for MM2
}

variable "tags" {
  type    = map(string)
  default = {}
}
