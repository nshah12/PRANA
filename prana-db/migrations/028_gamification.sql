-- Migration 028: Gamification — career score, badges, streaks
-- Tables: badge_definition, employee_badge, career_score, employee_streak
-- No raw salary or PAN in any gamification table.

-- ── Badge definitions (seeded, platform-managed) ─────────────────────────────

CREATE TABLE badge_definition (
    badge_definition_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    badge_key            VARCHAR(50)  NOT NULL UNIQUE,
    badge_name           VARCHAR(100) NOT NULL,
    badge_description    TEXT,
    badge_icon           VARCHAR(10)  NOT NULL,  -- emoji
    category             VARCHAR(30)  NOT NULL,  -- 'vault' | 'engagement' | 'career'
    sort_order           SMALLINT     NOT NULL DEFAULT 0,
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── Employee earned badges ────────────────────────────────────────────────────

CREATE TABLE employee_badge (
    employee_badge_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_user_id     UUID         NOT NULL REFERENCES employee_user(employee_user_id),
    badge_definition_id  UUID         NOT NULL REFERENCES badge_definition(badge_definition_id),
    context_key          VARCHAR(50)  NOT NULL DEFAULT '',  -- e.g. '2024-25' for fiscal-year badges
    earned_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    context              JSONB        NOT NULL DEFAULT '{}',
    UNIQUE (employee_user_id, badge_definition_id, context_key)
);

CREATE INDEX idx_emp_badge_user ON employee_badge (employee_user_id);

-- ── Career score (upserted on every recalculation) ───────────────────────────

CREATE TABLE career_score (
    employee_user_id     UUID         PRIMARY KEY REFERENCES employee_user(employee_user_id),
    score                SMALLINT     NOT NULL DEFAULT 0,  -- 0–100
    completeness_pts     SMALLINT     NOT NULL DEFAULT 0,  -- 0–40
    freshness_pts        SMALLINT     NOT NULL DEFAULT 0,  -- 0–30
    diversity_pts        SMALLINT     NOT NULL DEFAULT 0,  -- 0–20
    engagement_pts       SMALLINT     NOT NULL DEFAULT 0,  -- 0–10
    last_calculated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── Check-in streaks ─────────────────────────────────────────────────────────

CREATE TABLE employee_streak (
    employee_user_id     UUID         PRIMARY KEY REFERENCES employee_user(employee_user_id),
    current_streak_days  SMALLINT     NOT NULL DEFAULT 0,
    longest_streak_days  SMALLINT     NOT NULL DEFAULT 0,
    last_checkin_date    DATE,
    streak_started_date  DATE,
    total_checkins       INTEGER      NOT NULL DEFAULT 0,
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── Seed: badge definitions ───────────────────────────────────────────────────

INSERT INTO badge_definition (badge_key, badge_name, badge_description, badge_icon, category, sort_order) VALUES
  ('VAULT_STARTER',     'Vault Starter',        'First document routed to your vault',                          '📄', 'vault',      1),
  ('TAX_READY',         'Tax Ready',             'Have at least one Form 16 in your vault',                     '📊', 'vault',      2),
  ('FULL_YEAR',         'Full Year',             'All 12 salary slips for a fiscal year',                       '🗓️', 'vault',      3),
  ('CAREER_CHRONICLER', 'Career Chronicler',     'Five or more document types in your vault',                   '📚', 'vault',      4),
  ('MULTI_ORG',         'Multi-Org Veteran',     'Career documents from three or more employers',               '🏢', 'career',     5),
  ('CAREER_DECADE',     'Decade of Growth',      'Career timeline spanning 10 or more years',                   '🏆', 'career',     6),
  ('STREAK_3',          '3-Day Streak',          'Checked in 3 days in a row',                                  '🔥', 'engagement', 7),
  ('STREAK_7',          'Week Warrior',          'Checked in 7 days in a row',                                  '⚡', 'engagement', 8),
  ('STREAK_30',         'Monthly Champion',      'Checked in 30 days in a row',                                 '👑', 'engagement', 9),
  ('ASK_CURIOUS',       'Curious Mind',          'Asked Ask PRANA 5 questions',                                 '🤔', 'engagement', 10);
