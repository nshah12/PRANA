-- 046_webhook_delivery_log.sql
-- webhook_delivery_log — durable delivery record for WebhookDeliveryWorkflow
-- (workflows/platform_ops.py). Previously that workflow's deliver_webhook /
-- mark_webhook_failed activities were bare stubs with nowhere to persist an
-- outcome even once implemented.

CREATE TABLE IF NOT EXISTS webhook_delivery_log (
  delivery_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID         REFERENCES tenant(tenant_id),
  webhook_url   TEXT         NOT NULL,
  event_type    VARCHAR(60)  NOT NULL,
  status        VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                 -- PENDING | DELIVERED | FAILED
  response_code SMALLINT,
  attempt_count SMALLINT     NOT NULL DEFAULT 0,
  last_attempt_at TIMESTAMPTZ,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_delivery_tenant ON webhook_delivery_log(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_webhook_delivery_failed ON webhook_delivery_log(status) WHERE status = 'FAILED';

-- ROLLBACK:
-- DROP INDEX IF EXISTS idx_webhook_delivery_failed;
-- DROP INDEX IF EXISTS idx_webhook_delivery_tenant;
-- DROP TABLE IF EXISTS webhook_delivery_log;
