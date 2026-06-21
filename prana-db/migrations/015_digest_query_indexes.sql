-- Migration 015: Add indexes required for digest date-range queries
-- These five indexes eliminate full-tenant-scans on the core digest query patterns.
-- All are non-blocking CONCURRENTLY creates — safe on live YugabyteDB.

-- CHRO: documents pushed in a date window (most critical — every CHRO digest query)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_doc_tenant_pushed
    ON document (tenant_id, pushed_at DESC)
    WHERE is_deleted = FALSE;

-- CHRO/CFO: audit events filtered by event_type per tenant (alumni, session revocation)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_tenant_type
    ON audit_event (tenant_id, event_type, occurred_at DESC);

-- CISO: historical anomaly review — non-OPEN statuses (existing partial idx only covers OPEN)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_anomaly_tenant_detected
    ON anomaly_event (tenant_id, detected_at DESC);

-- CISO: access by channel breakdown — avoids in-memory filter after tenant scan
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dal_tenant_channel
    ON document_access_log (tenant_id, access_channel, accessed_at DESC);

-- CFO: exits/joiners filtered by event_type — avoids in-memory filter after tenant scan
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ce_tenant_type
    ON career_event (tenant_id, event_type, event_date DESC);
