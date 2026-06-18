-- Migration 011: service_incident table for PA health monitoring
-- Created by SystemHealthWorkflow; displayed in PA IncidentRegister

CREATE TABLE IF NOT EXISTS service_incident (
  incident_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  service_name      VARCHAR(50)  NOT NULL,   -- prana-api | prana-ai | prana-ask | kafka | redis | db
  severity          VARCHAR(20)  NOT NULL,   -- P1 | P2 | P3
  status            VARCHAR(20)  NOT NULL DEFAULT 'OPEN',  -- OPEN | ACKNOWLEDGED | RESOLVED
  title             TEXT         NOT NULL,
  detail            TEXT,                    -- raw error / HTTP status from health check
  detected_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  acknowledged_at   TIMESTAMPTZ,
  acknowledged_by   UUID,                    -- pa_id of PA who acknowledged
  resolved_at       TIMESTAMPTZ,
  resolved_by       UUID,                    -- pa_id who marked resolved
  resolution_note   TEXT,
  notified_at       TIMESTAMPTZ,             -- when PA email/SMS was sent
  check_url         VARCHAR(500)             -- which health endpoint failed
);

CREATE INDEX IF NOT EXISTS idx_service_incident_status   ON service_incident(status);
CREATE INDEX IF NOT EXISTS idx_service_incident_detected ON service_incident(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_incident_service  ON service_incident(service_name, status);

-- ROLLBACK:
-- DROP TABLE IF EXISTS service_incident;
