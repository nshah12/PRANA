#!/bin/sh
set -e
B=kafka:9093
# Full 21-topic list, matching prana-api/kafka/producer.py's TOPIC_* constants
# exactly. This file previously created only 5 of the 21 -- the rest existed on
# live dev Kafka only because they'd been created ad hoc at some point, and one
# (prana.cache.invalidation) never was, silently hanging every OA-user-creation
# request until traced back here. See prana-docs/PREPROD_TESTING_CHECKLIST.md
# §0 for the pre-prod-time check this same class of gap requires.
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.ingest.events        --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.pipeline.events       --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.audit.events           --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.notifications          --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.analytics.events        --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.vault.events           --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.auth.events            --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.employee.events        --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.tenant.events           --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.oa_users.events         --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.compliance.events        --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.security.events         --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.statutory.events        --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.integrations.events       --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.platform.events         --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.cache.invalidation        --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.notifications.email       --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.notifications.sms        --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.notifications.push       --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.notifications.whatsapp     --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.notifications.portal_bell   --partitions 12 --replication-factor 1
echo "Kafka topics created (21/21)"
