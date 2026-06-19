#!/bin/sh
set -e
B=kafka:9093
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.ingest.events    --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.pipeline.events  --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.audit.events     --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.notifications    --partitions 12 --replication-factor 1
kafka-topics --bootstrap-server $B --create --if-not-exists --topic prana.analytics.events --partitions 12 --replication-factor 1
echo "Kafka topics created"
