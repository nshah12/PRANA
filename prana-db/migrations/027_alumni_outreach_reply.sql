-- Migration 027: add reply_body to alumni_outreach for employee replies
-- Employee can reply to CHRO in-app outreach messages.
-- Single reply per message (one-to-one conversation thread for MVP).

ALTER TABLE alumni_outreach
  ADD COLUMN IF NOT EXISTS reply_body TEXT CHECK (LENGTH(reply_body) <= 2000);

COMMENT ON COLUMN alumni_outreach.reply_body IS
  'Employee reply text (plain text, max 2000 chars). NULL = not yet replied.';
