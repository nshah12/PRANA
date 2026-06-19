#!/bin/sh
set -e

echo "Waiting for YugabyteDB on yugabyte:5433..."
until bin/ysqlsh -h yugabyte -p 5433 -U yugabyte -c "SELECT 1" > /dev/null 2>&1; do
  sleep 3
done
echo "YugabyteDB ready."

bin/ysqlsh -h yugabyte -p 5433 -U yugabyte -c "CREATE DATABASE prana;" 2>/dev/null || true

bin/ysqlsh -h yugabyte -p 5433 -U yugabyte -d prana -f /prana-db/schema.sql
echo "Schema applied."

bin/ysqlsh -h yugabyte -p 5433 -U yugabyte -d prana -f /prana-db/seeds/dev_seed.sql
echo "Base seed done."

bin/ysqlsh -h yugabyte -p 5433 -U yugabyte -d prana -f /prana-db/seeds/dev_seed_emp_auth.sql
echo "Auth seed done."

bin/ysqlsh -h yugabyte -p 5433 -U yugabyte -d prana -f /prana-db/seeds/dev_seed_rich10.sql
echo "Rich seed done."

echo "DB init complete."
