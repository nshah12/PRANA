-- CISO dashboard seed data for techcorp.in
-- Provides realistic anomaly events, flagged login attempts, and OA audit events

DO $$
DECLARE
  v_tenant  UUID := '10000000-0000-0000-0000-000000000001';
  v_ciso_id UUID := '20000000-0001-0000-0000-000000000003';
  v_oa1     UUID := '20000000-0001-0000-0000-000000000001';  -- OA-Admin
  v_oa2     UUID := '20000000-0001-0000-0000-000000000002';  -- OA-Operator
  v_now     TIMESTAMPTZ := NOW();
BEGIN

-- ── Anomaly Events ────────────────────────────────────────────────────────────
INSERT INTO anomaly_event (anomaly_id, tenant_id, rule_name, severity, actor_id, status, detected_at, event_metadata) VALUES
  (gen_random_uuid(), v_tenant, 'Brute force login detected',            'P0', NULL,   'OPEN',         v_now - INTERVAL '2 hours',   '{"ip":"185.220.101.47","attempts":18,"window_minutes":10}'),
  (gen_random_uuid(), v_tenant, 'Credential stuffing attempt',           'P0', NULL,   'OPEN',         v_now - INTERVAL '5 hours',   '{"ip":"45.155.205.33","user_agents":12}'),
  (gen_random_uuid(), v_tenant, 'Mass document access from single IP',   'P1', v_oa2,  'OPEN',         v_now - INTERVAL '1 day',     '{"ip":"103.21.58.10","doc_count":47,"window_minutes":30}'),
  (gen_random_uuid(), v_tenant, 'OA account login from new country',     'P1', v_oa1,  'OPEN',         v_now - INTERVAL '18 hours',  '{"ip":"91.108.4.200","country":"RU","usual_country":"IN"}'),
  (gen_random_uuid(), v_tenant, 'TOTP bypass attempt',                   'P1', NULL,   'OPEN',         v_now - INTERVAL '3 days',    '{"ip":"62.113.201.55","attempts":5}'),
  (gen_random_uuid(), v_tenant, 'Unusual after-hours OA activity',       'P2', v_oa2,  'OPEN',         v_now - INTERVAL '2 days',    '{"hour_utc":2,"action_count":23}'),
  (gen_random_uuid(), v_tenant, 'Document bulk export pattern',          'P2', v_oa1,  'OPEN',         v_now - INTERVAL '4 days',    '{"export_count":31,"window_hours":2}'),
  (gen_random_uuid(), v_tenant, 'Failed TOTP — 3 consecutive attempts',  'P2', NULL,   'ACKNOWLEDGED', v_now - INTERVAL '5 days',    '{"ip":"103.27.120.88","user":"operator@techcorp.in"}'),
  (gen_random_uuid(), v_tenant, 'Shared session token reuse detected',   'P1', NULL,   'RESOLVED',     v_now - INTERVAL '6 days',    '{"session_id":"sess-abc123","reuse_count":3}'),
  (gen_random_uuid(), v_tenant, 'API key used from unexpected IP range',  'P2', NULL,   'RESOLVED',     v_now - INTERVAL '7 days',    '{"api_key_prefix":"pk_live_...","ip":"52.14.90.12"}');

-- ── Flagged Login Attempts ────────────────────────────────────────────────────
INSERT INTO login_attempt_log (
  attempt_id, tenant_id, user_type, user_id, identifier_hash,
  attempt_type, outcome, failure_reason,
  ip_address, ip_country, ip_city,
  user_agent, is_flagged, flag_reason, consecutive_failures,
  is_vpn_or_proxy, is_tor, ip_risk_score,
  attempted_at
) VALUES
  (gen_random_uuid(), v_tenant, 'OA', NULL, md5('unknown1@techcorp.in'),
   'PASSWORD', 'FAILED', 'INVALID_CREDENTIALS',
   '185.220.101.47', 'DE', 'Frankfurt',
   'Mozilla/5.0 (compatible; MSIE 9.0)', TRUE, 'BRUTE_FORCE', 18,
   TRUE, FALSE, 0.92, v_now - INTERVAL '2 hours'),

  (gen_random_uuid(), v_tenant, 'OA', NULL, md5('admin@techcorp.in'),
   'PASSWORD', 'BLOCKED', 'RATE_LIMITED',
   '45.155.205.33', 'NL', 'Amsterdam',
   'python-requests/2.31.0', TRUE, 'CREDENTIAL_STUFFING', 12,
   FALSE, TRUE, 0.98, v_now - INTERVAL '5 hours'),

  (gen_random_uuid(), v_tenant, 'OA', v_oa1, md5('admin@techcorp.in'),
   'TOTP', 'FAILED', 'INVALID_TOTP',
   '91.108.4.200', 'RU', 'Moscow',
   'Mozilla/5.0 (Windows NT 10.0; Win64)', TRUE, 'IMPOSSIBLE_TRAVEL', 3,
   FALSE, FALSE, 0.85, v_now - INTERVAL '18 hours'),

  (gen_random_uuid(), v_tenant, 'OA', v_oa2, md5('operator@techcorp.in'),
   'TOTP', 'FAILED', 'INVALID_TOTP',
   '103.27.120.88', 'IN', 'Delhi',
   'Mozilla/5.0 (Macintosh; Intel Mac OS X)', TRUE, 'REPEATED_TOTP_FAIL', 3,
   FALSE, FALSE, 0.55, v_now - INTERVAL '5 days'),

  (gen_random_uuid(), v_tenant, 'OA', NULL, md5('cfo@techcorp.in'),
   'PASSWORD', 'FAILED', 'INVALID_CREDENTIALS',
   '62.113.201.55', 'GB', 'London',
   'curl/7.88.1', TRUE, 'AUTOMATED_TOOL', 5,
   TRUE, FALSE, 0.75, v_now - INTERVAL '3 days'),

  (gen_random_uuid(), v_tenant, 'OA', v_oa1, md5('admin@techcorp.in'),
   'PASSWORD', 'FAILED', 'INVALID_CREDENTIALS',
   '103.21.58.10', 'IN', 'Mumbai',
   'Mozilla/5.0 (X11; Linux x86_64)', TRUE, 'UNUSUAL_HOUR', 1,
   FALSE, FALSE, 0.40, v_now - INTERVAL '2 days');

-- ── OA Audit Events ───────────────────────────────────────────────────────────
INSERT INTO audit_event (event_id, tenant_id, event_type, actor_type, actor_id, document_id, ip_address, occurred_at, event_metadata) VALUES
  (gen_random_uuid(), v_tenant, 'DOCUMENT_ACCESSED',  'OA_OPERATOR', v_oa2, NULL, '103.21.58.10', v_now - INTERVAL '1 hour',   '{"doc_count":47}'),
  (gen_random_uuid(), v_tenant, 'EMPLOYEE_UNLOCKED',  'OA_ADMIN',    v_oa1, NULL, '49.207.66.123', v_now - INTERVAL '3 hours', '{"employee_id":"emp-001"}'),
  (gen_random_uuid(), v_tenant, 'EXCEPTION_RESOLVED', 'OA_ADMIN',    v_oa1, NULL, '49.207.66.123', v_now - INTERVAL '6 hours', '{"exception_id":"ex-001"}'),
  (gen_random_uuid(), v_tenant, 'DOCUMENT_ACCESSED',  'OA_OPERATOR', v_oa2, NULL, '103.21.58.10', v_now - INTERVAL '1 day',   '{"doc_count":12}'),
  (gen_random_uuid(), v_tenant, 'EMPLOYEE_LOCKED',    'OA_ADMIN',    v_oa1, NULL, '49.207.66.123', v_now - INTERVAL '2 days',  '{"reason":"SUSPICIOUS_ACTIVITY"}'),
  (gen_random_uuid(), v_tenant, 'ELEVATION_APPROVED', 'OA_ADMIN',    v_oa1, NULL, '49.207.66.123', v_now - INTERVAL '3 days',  '{"elevation_id":"el-001","duration_hours":2}'),
  (gen_random_uuid(), v_tenant, 'DOCUMENT_ACCESSED',  'OA_OPERATOR', v_oa2, NULL, '103.21.58.10', v_now - INTERVAL '4 days',  '{"doc_count":8}'),
  (gen_random_uuid(), v_tenant, 'DOCUMENT_ACCESSED',  'OA_OPERATOR_ELEVATED', v_oa2, NULL, '103.21.58.10', v_now - INTERVAL '5 days', '{"doc_count":31}');

END $$;
