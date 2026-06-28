import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'

// ── Gradient helpers ──────────────────────────────────────────────────────────
const GRAD = 'linear-gradient(135deg, #6366F1 0%, #22D3EE 55%, #34D399 100%)'

function GradText({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={className}
      style={{ background: GRAD, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
      {children}
    </span>
  )
}

function GradBtn({ children, onClick, type = 'button', className = '' }: {
  children: React.ReactNode; onClick?: () => void; type?: 'button' | 'submit'; className?: string
}) {
  return (
    <button type={type} onClick={onClick}
      style={{ background: GRAD }}
      className={`text-white font-semibold rounded-xl px-6 py-3 text-sm hover:opacity-90 transition-opacity ${className}`}>
      {children}
    </button>
  )
}

// ── Content data ──────────────────────────────────────────────────────────────

const HIW_STEPS = [
  { n: '01', icon: '🏢', title: 'Employer onboards', desc: 'HR registers on PRANA portal in 15 min. Domain-verified. KEK-provisioned. Ready.' },
  { n: '02', icon: '📥', title: 'Documents arrive', desc: 'Salary slips, Form 16, offer letters — pushed automatically via portal or HRMS API.' },
  { n: '03', icon: '🤖', title: 'AI extracts insights', desc: '6-stage pipeline: OCR → classification → extraction → resolution → routing. Raw ₹ never stored.' },
  { n: '04', icon: '🗄', title: 'Vault activated', desc: 'One permanent vault. Every employer adds to the same vault — across your entire career.' },
  { n: '05', icon: '↗', title: 'You share securely', desc: 'Pick documents, set expiry, generate a watermarked C-Share link. Banks receive in seconds.' },
  { n: '06', icon: '✓', title: 'Recipient verifies', desc: 'QR scan confirms authenticity. Cryptographic proof. No phone calls to HR needed.' },
]

const EMPLOYEE_FEATURES = [
  { icon: '🗄',  title: 'My Vault',           desc: 'All documents, all employers, one place. The core promise.',                          accent: '#6366F1', bg: '#EEF2FF' },
  { icon: '↗',  title: 'C-Share',             desc: 'Create, revoke, watermark, set expiry, view count. You control every share.',         accent: '#0EA5E9', bg: '#F0F9FF' },
  { icon: '📋',  title: 'Activity log',        desc: 'Every access, push, and share event. Full transparency. No black boxes.',             accent: '#8B5CF6', bg: '#F5F3FF' },
  { icon: '🔔',  title: 'Smart alerts',        desc: 'Document arrived, accessed, share expiring. The vault that watches out for you.',     accent: '#F59E0B', bg: '#FFFBEB' },
  { icon: '⚖',  title: 'DPDP Rights Centre',  desc: 'Access, Correction, Erasure, Grievance, Nomination, Consent — all 6 rights.',        accent: '#EF4444', bg: '#FEF2F2' },
  { icon: '📅',  title: 'Career Timeline',     desc: 'Auto-assembled from verified documents. AI built your career story.',                 accent: '#10B981', bg: '#ECFDF5' },
  { icon: '📊',  title: 'Vault Health Score',  desc: 'Document completeness %. Shows gaps you never knew existed. Actionable.',            accent: '#06B6D4', bg: '#ECFEFF' },
  { icon: '📦',  title: 'Share Bundles',       desc: 'Named collections for loan, BGV, visa. One link. Everything the recipient needs.',    accent: '#EC4899', bg: '#FDF2F8' },
]

const CHRO_FEATURES = [
  { icon: '📊', title: 'Vault Health Dashboard', desc: 'Document completeness per department, grade, location — refreshed daily from verified pushes.' },
  { icon: '📅', title: 'Compliance Calendar',    desc: 'Form 16 deadlines, PF/ESIC obligations, DPDP consent review cycles — never miss a date.' },
  { icon: '📧', title: 'Weekly & Monthly Digest',desc: 'Vault completeness trends, new joiners, missing documents — delivered automatically.' },
  { icon: '🔔', title: 'Alert Config',           desc: 'Set thresholds on completeness, anomalies, consent drop-off. Proactive, not reactive.' },
]

const CFO_FEATURES = [
  { icon: '💰', title: 'Payroll Intelligence',   desc: 'Aggregate compensation analytics from verified salary slips. No individual salary ever visible. Min 30-person cohort.' },
  { icon: '📉', title: 'Attrition Cost',         desc: 'Replacement cost modelling from verified exit data. ₹ per exit, by department.' },
  { icon: '🔍', title: 'Anomaly Detection',      desc: 'Discrepancies between salary slips and appointment letters caught by AI — before they become liabilities.' },
  { icon: '📋', title: 'Compliance Posture',     desc: 'DPDP exposure, obligation tracking, consent coverage. Estimated penalty risk surfaced proactively.' },
]

const CISO_LAYERS = [
  { n: '1', label: 'STRUCTURAL',     title: 'Vault ownership transfers on routing',       desc: 'Employer cannot open, download, share, or delete. Ownership moved structurally.' },
  { n: '2', label: 'CRYPTOGRAPHIC',  title: 'One person. One key. One vault.',             desc: 'Each employee has their own DEK. A colleague\'s key cannot decrypt yours.' },
  { n: '3', label: 'ZERO-KNOWLEDGE', title: 'The system doesn\'t know who you are.',       desc: 'PAN → HMAC in 2ms. Plaintext destroyed. No row links PAN to name.' },
  { n: '4', label: 'CONSENT-GATED',  title: 'Sharing requires your action. Always.',      desc: 'Only you create share tokens. Named, time-limited, revocable, watermarked.' },
  { n: '5', label: 'RLS ENFORCED',   title: 'Portal Admin cannot read documents.',         desc: 'Zero SELECT on document rows. PostgreSQL RLS. The query is refused at DB level.' },
  { n: '6', label: 'TRANSPARENT',    title: 'Every access visible to the document owner.', desc: 'Actor, timestamp, action — in the employee\'s activity log. No black boxes.' },
  { n: '7', label: 'PORTABLE',       title: 'Your vault follows you — not your employer.', desc: 'When you leave, your vault stays yours. New employer pushes to the same vault.' },
]

const CISO_STATS = [
  { value: '1',      label: 'Person exposed per DEK compromise' },
  { value: '0',      label: 'Plaintext PAN in any DB row' },
  { value: '2ms',    label: 'PAN lifetime in memory' },
  { value: '₹150Cr', label: 'Max DPDP penalty — misuse structurally impossible' },
]

const ORG_FEATURES = [
  { icon: '⬆',  role: 'OA-Operator', title: 'Bulk upload with AI governance',   desc: 'Content policy, contamination detection, independent AI classification on every push.' },
  { icon: '👥',  role: 'OA-Admin',    title: 'User management & elevations',      desc: 'Self-managed org. Minimum-1-admin enforced. Elevation approvals with full audit trail.' },
  { icon: '🔌',  role: 'IT / DevOps', title: 'HRMS API integration',             desc: 'OpenAPI-compatible. X-PRANA-Key-ID + HMAC-SHA256. 500 rpm. Push millions of docs automatically.' },
  { icon: '🔑',  role: 'Security',    title: 'Platform-managed KEK/DEK',         desc: 'AWS KMS (ap-south-1). Tenant KEK + per-employee DEK. Blast radius = 1 person.' },
]

const TRUST_STATS = [
  { value: '6-stage', label: 'AI pipeline' },
  { value: 'DPDP',    label: 'Act 2023 ready' },
  { value: '0 raw ₹', label: 'ever stored' },
  { value: 'AES-256', label: 'at rest + transit' },
  { value: '7-year',  label: 'audit retention' },
  { value: 'DEK/KEK', label: 'per-employee encryption' },
]

const PERSONAS = [
  { id: 'employee', label: 'For Employees',       icon: '👤', color: '#0EA5E9' },
  { id: 'chro',     label: 'For CHRO / HR Heads', icon: '📊', color: '#10B981' },
  { id: 'cfo',      label: 'For CFO / Finance',   icon: '💰', color: '#6366F1' },
  { id: 'ciso',     label: 'For Infosec / DPO',   icon: '🛡', color: '#EF4444' },
]

// ── FAQ data ──────────────────────────────────────────────────────────────────

const FAQ_ROLES = [
  { id: 'employee', label: 'Employee',     color: '#0EA5E9', bg: '#F0F9FF', border: '#BAE6FD' },
  { id: 'chro',     label: 'CHRO / HR',    color: '#10B981', bg: '#ECFDF5', border: '#A7F3D0' },
  { id: 'ciso',     label: 'CISO / InfoSec', color: '#F59E0B', bg: '#FFFBEB', border: '#FDE68A' },
  { id: 'cfo',      label: 'CFO',          color: '#6366F1', bg: '#EEF2FF', border: '#C7D2FE' },
]

const FAQ_DATA: Record<string, { cat: string; q: string; a: string }[]> = {
  employee: [
    { cat: 'Access', q: 'Where do I get the PRANA app?', a: 'Download from the App Store or Play Store — search "PRANA Vault". Log in with the mobile number your employer registered. You get an OTP on first login; no password needed.' },
    { cat: 'Documents', q: 'Which documents will I find in my vault?', a: 'Salary slips, Form 16, offer letters, relieving letters, increment letters, PF statements — pushed by your employer. You can also self-upload documents; they are marked "Unverified — self-uploaded".' },
    { cat: 'Documents', q: 'I changed jobs — what happens to my old employer\'s documents?', a: 'They stay permanently in your vault under that employer\'s section. PRANA is a lifelong vault — documents never disappear when you leave. New employer documents appear separately.' },
    { cat: 'Privacy', q: 'Can my current employer see documents from a previous employer?', a: 'No. Documents are strictly tenant-isolated. Each employer sees only what they pushed. No employer can access another employer\'s documents or your full vault.' },
    { cat: 'Privacy', q: 'Is my salary stored anywhere in PRANA?', a: 'No. PRANA never stores raw salary figures. The AI extracts insights — like "your salary is competitive for your band" — but the number itself is never written to any database, never shown in the app, and never accessible to anyone.' },
    { cat: 'Privacy', q: 'Is my PAN visible anywhere in the app?', a: 'Never. PAN is not displayed anywhere in PRANA — not masked, not partial. It is stored in encrypted form only, used internally for identity matching, and never surfaced in any UI.' },
    { cat: 'Sharing', q: 'How do I share a salary slip with a bank for a loan?', a: 'Open the document → tap Share → enter the recipient\'s phone or email. They get an OTP and can view the document for 10 minutes — watermarked with their name, your name, and the timestamp. They cannot download a clean copy. You can revoke anytime.' },
    { cat: 'Career Score', q: 'What is the Career Score?', a: 'A 0–100 score reflecting vault completeness (40%), document freshness (30%), diversity (20%), and engagement (10%). A vault health indicator — not a creditworthiness score.' },
    { cat: 'Rights', q: 'Can I ask PRANA to delete all my data?', a: 'Yes. Under DPDP Act 2023 you have the right to erasure. Go to Settings → Data Rights → Request Erasure. Processed within 30 days. Audit logs are retained for 7 years as required by law — you are told this upfront.' },
    { cat: 'Rights', q: 'Can I download everything PRANA has on me?', a: 'Yes. Settings → Data Rights → Export My Data. You get a zip file within 72 hours containing all your documents, career timeline, and access log.' },
    { cat: 'Rights', q: 'Can I withdraw my data processing consent?', a: 'Yes — Settings → Privacy → Manage Consent. Withdrawing stops all future processing for that purpose immediately. You can withdraw selectively per purpose (e.g. withdraw analytics but keep vault access).' },
    { cat: 'Security', q: 'What if I lose my phone?', a: 'Log in from any browser with OTP → Settings → Devices → Revoke this device. All sessions on the lost phone terminate within seconds. Nothing is stored on the device.' },
    { cat: 'Ask PRANA', q: 'What can I ask the PRANA chatbot?', a: 'Career questions in plain English or Hindi: "When did I join TechCorp?", "Do I have Form 16 for FY 2023?". It cannot tell you salary figures — those are never stored.' },
  ],
  chro: [
    { cat: 'Integration', q: 'How does PRANA connect to our HRMS (Darwinbox / Keka / SAP)?', a: 'Native connectors for Darwinbox and Keka. Two modes: Pull (PRANA fetches on schedule — default 6 hours) or Webhook (HRMS pushes changes in real time). Configure credentials once in Portal → HRMS Integration. All credentials are KMS-encrypted at write time.' },
    { cat: 'Documents', q: 'What document types does PRANA support?', a: '14 types: salary slip, Form 16, offer letter, relieving letter, increment letter, appointment letter, PF statement, ESI document, bonus letter, promotion letter, experience letter, appraisal letter, training certificate, identity proof. Custom types can be added via manifest configuration.' },
    { cat: 'Documents', q: 'Can we push documents for contract workers?', a: 'Yes — any individual with a registered mobile number and PAN can have a vault. Contract workers are onboarded identically to full-time employees. Their documents are isolated to your tenant.' },
    { cat: 'Operations', q: 'What happens to an employee\'s vault when they leave?', a: 'Their status becomes ALUMNI. Existing documents remain in their vault permanently — they still own access. You stop being able to push new documents. You can configure a grace period for access log retention.' },
    { cat: 'Operations', q: 'We pushed a wrong salary slip. Can we replace it?', a: 'Yes — upload the corrected version via Portal → Upload. The old document is superseded (marked replaced) but retained in audit history. The employee sees the updated version. Both are logged with timestamps.' },
    { cat: 'Operations', q: 'What is the exception queue?', a: 'When PRANA can\'t match a document to an employee (name mismatch, no PAN), it goes to the exception queue. Your OA-Operator manually links and resolves it. SLA: 4 hours (P50), 24 hours (P95).' },
    { cat: 'Operations', q: 'Can we do a bulk historical upload?', a: 'Yes — drag-and-drop a ZIP with a CSV manifest in Portal → Batch Upload. PRANA fans out to process each document in parallel. Per-file progress shows in real time via the pipeline status tracker.' },
    { cat: 'Compliance', q: 'What happens if an employee files a DPDP erasure request?', a: 'You are notified via the Portal. A workflow manages the SLA (30 days for erasure, 15 days for correction). PRANA auto-escalates to your Grievance Officer if unresolved. Audit logs are exempt from erasure.' },
    { cat: 'Compliance', q: 'Does PRANA help with Form 16 issuance deadlines?', a: 'Yes. The Compliance Calendar shows statutory due dates. When you push Form 16s, the compliance posture view updates to show coverage % per employee. You get alerts for employees who haven\'t received Form 16 before the deadline.' },
    { cat: 'Analytics', q: 'What is vault completeness?', a: 'A per-employee score showing what % of expected document types are present and current. Shown aggregated by department and grade in your CHRO dashboard. Low completeness triggers alerts so you can chase missing documents before audit.' },
    { cat: 'Analytics', q: 'Can CHRO see employees\' actual salary figures?', a: 'No. PRANA never stores salary amounts. The CHRO dashboard shows completion rates, document counts, and insight-level summaries. Raw salary data is not accessible to anyone — including PRANA\'s own staff.' },
    { cat: 'Integration', q: 'What if the HRMS sync fails?', a: 'The OA-Admin and Grievance Officer for your tenant receive an alert. The failed sync is logged in HRMS Integration → Sync History with an error reason. You can trigger a manual re-sync from the Portal without waiting for the next scheduled run.' },
    { cat: 'Multi-org', q: 'An employee worked at two of our group companies — duplicate vaults?', a: 'No. PRANA deduplicates by PAN token (a one-way hash — the actual PAN is never stored). An employee at two group companies has one vault with two employer sections. Career insights span the full tenure across all employers.' },
  ],
  ciso: [
    { cat: 'Storage', q: 'Where is the data physically stored?', a: 'AWS ap-south-1 (Mumbai) primary, ap-south-2 (Hyderabad) secondary. YugabyteDB for structured data, AWS S3 for document bytes. No data leaves India. Audit logs older than 2 years move to Apache Iceberg on S3 (cold archive).' },
    { cat: 'Encryption', q: 'What encryption is used at rest and in transit?', a: 'In transit: TLS 1.3 everywhere. At rest: S3 documents encrypted with tenant-specific DEKs, envelope-encrypted with tenant KEKs in AWS KMS (customer-managed, ap-south-1). DB fields: FF3-1 format-preserving encryption for PAN, AES-256-GCM for TOTP secrets.' },
    { cat: 'Encryption', q: 'Is PAN stored in plaintext anywhere?', a: 'Never. PAN → HMAC-SHA256 → pan_token (one-way, safe dedup key) OR FF3-1 FPE → enc_pan (reversible only with employee\'s DEK). Plaintext PAN never touches the DB, cache, logs, or API responses.' },
    { cat: 'Encryption', q: 'Who holds the KMS keys?', a: 'AWS KMS customer-managed keys. Platform_secret and tenant KEKs are managed via AWS IAM roles — no standing access for PRANA engineers. Tenant KEKs are per-organisation, never shared across tenants. Key rotation is tracked in the kms_key_log table.' },
    { cat: 'Access', q: 'What MFA is enforced?', a: 'All OA users and Portal Admins require TOTP (Google Authenticator-compatible) in addition to password. Employees use OTP-per-session (SMS). Biometric re-auth for document access on mobile is enforced if enrolled.' },
    { cat: 'Access', q: 'Can PRANA engineers access our data?', a: 'No. There is no admin backdoor. Engineers have no standing access to tenant data. KMS key access requires IAM policy approval. All platform-level activity is logged to audit_event and visible to your CISO dashboard.' },
    { cat: 'Audit', q: 'What audit logs does PRANA produce?', a: 'Every action generates an audit_event row: document pushes, accesses, shares, logins, TOTP events, elevation approvals, DPDP requests, exceptions resolved, key rotations, config changes. Immutable — no DELETE on audit_event. 7-year retention.' },
    { cat: 'Audit', q: 'Can an employee\'s erasure request wipe audit logs?', a: 'No. DPDP erasure removes PII fields from employee tables. Audit logs are explicitly exempt under the legal retention exception — disclosed to the employee during the erasure flow.' },
    { cat: 'Sessions', q: 'Can we force-logout a user remotely?', a: 'Yes — CISO dashboard → Sessions → Revoke. Takes effect within one request cycle (Redis pub/sub). Works for any role. Elevation sessions can also be terminated early by the OA-Admin.' },
    { cat: 'Network', q: 'How are HRMS webhook calls authenticated?', a: 'Each connector has a webhook_secret. Incoming POSTs must include X-Prana-Webhook-Sig = HMAC-SHA256(raw_body, webhook_secret). PRANA verifies with hmac.compare_digest (timing-safe) before processing any payload. 401 on mismatch.' },
    { cat: 'Pipeline', q: 'Does the AI model see salary figures and PAN?', a: 'The extraction model receives full document text (needed for extraction). But its output contract is insights only. The pipeline strips all raw figures before any DB write (Stage 05→06). Rule: LLM input = full data. LLM output = insights only. Enforced in code, not just policy.' },
    { cat: 'Scanning', q: 'Are documents scanned for malware and CSAM?', a: 'Yes. Stage 03 runs ClamAV (malware), a NSFW classifier, and a CSAM hash-check against PhotoDNA. Any match triggers immediate quarantine — document is never routed to the vault. CSAM matches fire a reporting workflow as required by law.' },
    { cat: 'Incident', q: 'What is the breach response process?', a: 'AnomalyDetectionWorkflow fires alerts for anomalous access patterns (bulk downloads, foreign IPs, off-hours spikes). Your CISO dashboard shows flagged events. For confirmed breaches, PRANA supports immediate tenant-wide session revocation and can assist with CERT-In 6-hour notification requirements.' },
  ],
  cfo: [
    { cat: 'Privacy', q: 'Does PRANA store employee salary figures?', a: 'No. PRANA never stores raw salary amounts in any database, cache, log, or API response. The AI extracts insights only ("salary is above median for the band"). If you are ever asked to produce salary data from PRANA, it will not be there — by design.' },
    { cat: 'Liability', q: 'If an employee disputes a salary figure in PRANA, who is liable?', a: 'PRANA stores exactly what your payroll system pushed. If the figure is wrong, the source of truth is your HRMS/payroll system — PRANA is the vault, not the calculator. Liability for payroll accuracy remains with you. PRANA provides the paper trail (who pushed it, when, from which IP).' },
    { cat: 'Cost savings', q: 'How does PRANA reduce Form 16 issuance cost?', a: 'PRANA automates delivery — your TDS system pushes Form 16s via API and every employee gets it in their vault instantly. No printing, no courier, no chasing employees. Estimated saving: ₹40–120 per employee per year in distribution cost.' },
    { cat: 'Cost savings', q: 'Does PRANA help with DPDP Act compliance costs?', a: 'Yes. All 5 employee rights are handled by workflows with built-in SLA tracking and audit trails. PRANA reduces per-request cost from ₹2,000–5,000 (manual legal review) to near-zero (automated).' },
    { cat: 'Analytics', q: 'What financial analytics does PRANA provide for CFOs?', a: 'Payroll intelligence (document completeness by cost centre), attrition cost modelling, anomaly detection (unusual document requests that may indicate moonlighting or fraud), and compensation benchmarking (insight-level only — no raw figures). All in the CFO dashboard.' },
    { cat: 'Analytics', q: 'Can CFO see individual employee salary data?', a: 'No. CFO analytics are aggregated and insight-level only. PRANA cannot show you an individual\'s salary figure — it was never stored. Benchmarking is against anonymised cohort bands, not individual records.' },
    { cat: 'ROI', q: 'What is the ROI case for PRANA?', a: 'Four levers: (1) HR admin cost reduced ~80% for document distribution. (2) Attrition signal — vault completeness gaps correlate with resignation risk. (3) DPDP compliance — automated rights responses. (4) Audit cost — 7-year log retention reduces external audit time by 30–40%.' },
    { cat: 'Audit', q: 'Is PRANA useful during a statutory audit?', a: 'Yes. Auditors can be given read-only Portal access scoped to specific document types. PRANA\'s 7-year immutable audit log shows exactly who accessed what and when. You can pull a vault completeness report for any period in seconds.' },
    { cat: 'Audit', q: 'What happens to audit logs if we terminate the PRANA contract?', a: 'Audit logs are retained for 7 years regardless of contract status — this is a legal requirement. You receive an export of all logs at offboarding. Document bytes and employee records are erased on your timeline.' },
    { cat: 'Risk', q: 'Can a new employer access documents the previous employer pushed to an employee\'s vault?', a: 'No. Previous employer documents are accessible only to the employee, not to the new employer. A new employer cannot see what the previous employer pushed. There is no competitive data leakage risk.' },
    { cat: 'Risk', q: 'What if the PRANA service goes down — do we lose documents?', a: 'Documents are stored in AWS S3 (dual-region Mumbai + Hyderabad) with 11 nines of durability. The YugabyteDB database is dual-region active-active. PRANA\'s SLA is 99.9% uptime. Even in a full outage, documents are never lost.' },
    { cat: 'Privacy', q: 'Does PRANA share our employee data with third parties?', a: 'No. PRANA does not sell data, share data with advertisers, or use your employee data to train models. The LLM used for extraction runs on PRANA\'s own infrastructure. Data is processed solely to provide the PRANA service.' },
  ],
}

const CAT_COLORS: Record<string, string> = {
  Access: '#E0F2FE|#0369A1', Documents: '#DCFCE7|#15803D', Privacy: '#EDE9FE|#5B21B6',
  Sharing: '#D1FAE5|#065F46', 'Career Score': '#FEF3C7|#92400E', Rights: '#FEE2E2|#991B1B',
  Security: '#FEE2E2|#991B1B', 'Ask PRANA': '#FCE7F3|#9D174D', Integration: '#DBEAFE|#1E40AF',
  Operations: '#DCFCE7|#15803D', Compliance: '#EDE9FE|#5B21B6', Analytics: '#D1FAE5|#065F46',
  'Multi-org': '#FEF3C7|#92400E', Onboarding: '#DCFCE7|#15803D', Storage: '#FEE2E2|#991B1B',
  Encryption: '#FEF3C7|#92400E', Audit: '#D1FAE5|#065F46', Sessions: '#FEE2E2|#991B1B',
  Network: '#FCE7F3|#9D174D', Pipeline: '#DBEAFE|#1E40AF', Scanning: '#FEE2E2|#991B1B',
  Incident: '#FCE7F3|#9D174D', Liability: '#EDE9FE|#5B21B6', 'Cost savings': '#DCFCE7|#15803D',
  ROI: '#FCE7F3|#9D174D', Risk: '#FEE2E2|#991B1B',
}

function catStyle(cat: string) {
  const [bg, color] = (CAT_COLORS[cat] || '#F1F5F9|#475569').split('|')
  return { background: bg, color }
}

function FaqSection() {
  const [role, setRole] = useState('employee')
  const [search, setSearch] = useState('')
  const [openIdx, setOpenIdx] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim()
    if (!q) return FAQ_DATA
    const result: typeof FAQ_DATA = {}
    for (const [r, items] of Object.entries(FAQ_DATA)) {
      result[r] = items.filter(i =>
        i.q.toLowerCase().includes(q) || i.a.toLowerCase().includes(q) || i.cat.toLowerCase().includes(q)
      )
    }
    return result
  }, [search])

  const activeItems = search.trim()
    ? Object.values(filtered).flat()
    : (filtered[role] ?? [])

  const totalMatches = search.trim()
    ? Object.values(filtered).reduce((s, a) => s + a.length, 0)
    : null

  return (
    <section className="max-w-5xl mx-auto px-6 py-16">
      <div className="text-center mb-10">
        <p className="text-xs font-bold text-indigo-500 tracking-widest uppercase mb-3">FAQ</p>
        <h2 className="text-3xl font-extrabold text-slate-900 mb-3">
          Questions we hear <GradText>before they're asked</GradText>
        </h2>
        <p className="text-slate-400 text-sm max-w-lg mx-auto">
          Crispy answers for every role — Employee, CHRO, CISO, and CFO.
          Search across all roles or browse by tab.
        </p>
      </div>

      {/* Search */}
      <div className="relative mb-5">
        <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        <input
          type="text"
          value={search}
          onChange={e => { setSearch(e.target.value); setOpenIdx(null) }}
          placeholder="Search across all roles…"
          className="w-full pl-10 pr-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
        />
        {search && (
          <button onClick={() => { setSearch(''); setOpenIdx(null) }}
            className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-lg leading-none">✕</button>
        )}
      </div>

      {/* Role tabs — hidden when searching across all */}
      {!search.trim() && (
        <div className="flex flex-wrap gap-2 mb-6">
          {FAQ_ROLES.map(r => (
            <button key={r.id} onClick={() => { setRole(r.id); setOpenIdx(null) }}
              className="px-4 py-2 rounded-full text-xs font-semibold border transition-all"
              style={role === r.id
                ? { background: r.bg, color: r.color, borderColor: r.border }
                : { background: 'white', color: '#64748b', borderColor: '#e2e8f0' }}>
              {r.label}
            </button>
          ))}
        </div>
      )}

      {/* Match count when searching */}
      {search.trim() && totalMatches !== null && (
        <p className="text-xs text-slate-400 mb-4">
          {totalMatches === 0 ? 'No matching questions.' : `${totalMatches} question${totalMatches !== 1 ? 's' : ''} across all roles`}
        </p>
      )}

      {/* FAQ list */}
      <div className="space-y-2">
        {activeItems.length === 0 && (
          <p className="text-center py-10 text-slate-400 text-sm">No matching questions. Try a different keyword.</p>
        )}
        {activeItems.map((item, i) => {
          const key = `${role}-${i}`
          const isOpen = openIdx === key
          return (
            <div key={key} className="border border-slate-200 rounded-xl overflow-hidden hover:border-slate-300 transition-colors">
              <button
                onClick={() => setOpenIdx(isOpen ? null : key)}
                className="w-full flex items-center gap-3 px-5 py-4 bg-white text-left">
                <span className="flex-1 text-sm font-medium text-slate-800 leading-snug">{item.q}</span>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full flex-shrink-0"
                  style={catStyle(item.cat)}>{item.cat}</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2"
                  style={{ flexShrink: 0, transition: 'transform .2s', transform: isOpen ? 'rotate(180deg)' : 'none' }}>
                  <path d="m6 9 6 6 6-6"/>
                </svg>
              </button>
              {isOpen && (
                <div className="px-5 pb-4 pt-1 text-sm text-slate-600 leading-relaxed border-t border-slate-100 bg-slate-50">
                  {item.a}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* CTA */}
      {!search.trim() && (
        <div className="mt-8 text-center">
          <p className="text-xs text-slate-400 mb-3">Have a question that isn't answered here?</p>
          <a href="prana-docs/wireframes/PRANA_FAQ_by_Role.html" target="_blank" rel="noopener"
            className="text-xs font-semibold text-indigo-500 hover:underline mr-6">
            View full FAQ ↗
          </a>
        </div>
      )}
    </section>
  )
}

// ── Contact modal ─────────────────────────────────────────────────────────────
function ContactModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({ name: '', email: '', org: '', enquiry_type: 'Organisation onboarding', message: '' })
  const [sent, setSent] = useState(false)
  const sf = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))
  const mutation = useMutation({
    mutationFn: () => api.post('/public/contact', form),
    onSuccess: () => setSent(true),
  })
  const inp = "w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" />
      <div className="relative bg-white rounded-3xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-8 pt-7 pb-5 border-b border-slate-100">
          <div>
            <p className="text-xs font-bold text-indigo-500 tracking-widest uppercase mb-0.5">Get in touch</p>
            <h2 className="text-xl font-extrabold text-slate-900">Contact PRANA</h2>
          </div>
          <button onClick={onClose}
            className="w-8 h-8 rounded-xl bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-500 transition-colors">
            ✕
          </button>
        </div>

        <div className="px-8 py-6">
          {sent ? (
            <div className="text-center py-8">
              <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 text-3xl"
                style={{ background: 'linear-gradient(135deg, #10B981, #22D3EE)' }}>
                ✓
              </div>
              <h3 className="text-lg font-bold text-slate-800 mb-2">Message sent!</h3>
              <p className="text-slate-500 text-sm mb-6">We'll reply within 24 hours at <strong>{form.email}</strong>.</p>
              <button onClick={onClose}
                className="text-sm font-semibold text-indigo-600 border border-indigo-100 rounded-xl px-5 py-2.5 hover:bg-indigo-50 transition-colors">
                Close
              </button>
            </div>
          ) : (
            <form onSubmit={e => { e.preventDefault(); mutation.mutate() }} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Full name <span className="text-red-400">*</span></label>
                  <input className={inp} required value={form.name} onChange={sf('name')} placeholder="Priya Sharma" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Work email <span className="text-red-400">*</span></label>
                  <input className={inp} required type="email" value={form.email} onChange={sf('email')} placeholder="priya@company.in" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Organisation</label>
                  <input className={inp} value={form.org} onChange={sf('org')} placeholder="TechCorp Solutions Pvt Ltd" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Enquiry type</label>
                  <select className={inp} value={form.enquiry_type} onChange={sf('enquiry_type')}>
                    {['Organisation onboarding', 'Product demo', 'Partnership', 'HRMS integration', 'General / Support'].map(o => <option key={o}>{o}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">Message</label>
                <textarea className={`${inp} resize-none h-24`} value={form.message} onChange={sf('message')} placeholder="Tell us what you need…" />
              </div>
              {mutation.isError && <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">Failed to send. Please try again.</p>}
              <GradBtn type="submit" className="w-full !rounded-xl !py-3.5">
                {mutation.isPending ? 'Sending…' : 'Send message — we reply within 24 hours →'}
              </GradBtn>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export function Landing() {
  const navigate = useNavigate()
  const [activeStep, setActiveStep] = useState(0)
  const [hoveredStep, setHoveredStep] = useState<number | null>(null)
  const [persona, setPersona] = useState('employee')
  const [loginOpen, setLoginOpen] = useState(false)
  const [contactOpen, setContactOpen] = useState(false)
  const loginRef = useRef<HTMLDivElement>(null)
  const contactRef = useRef<HTMLDivElement>(null)
  const hiwRef = useRef<HTMLDivElement>(null)
  const personaRef = useRef<HTMLDivElement>(null)
  const faqRef = useRef<HTMLDivElement>(null)
  const openContact = useCallback(() => setContactOpen(true), [])

  useEffect(() => {
    const t = setInterval(() => setActiveStep(s => (s + 1) % 6), 2800)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    function h(e: MouseEvent) {
      if (loginRef.current && !loginRef.current.contains(e.target as Node)) setLoginOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  function scrollTo(ref: React.RefObject<HTMLDivElement>) {
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="min-h-screen bg-white font-sans">
      {contactOpen && <ContactModal onClose={() => setContactOpen(false)} />}

      {/* ── Navbar ── */}
      <nav className="sticky top-0 z-50 bg-white/90 backdrop-blur border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: GRAD }}>
              <span className="text-white font-bold text-sm">P</span>
            </div>
            <span className="font-mono font-bold text-slate-900 text-lg tracking-tight">
              PRANA<span className="text-indigo-500">·</span>
            </span>
          </div>

          <div className="hidden md:flex items-center gap-8">
            <button onClick={() => scrollTo(hiwRef)} className="text-sm font-semibold text-slate-700 hover:text-indigo-600 transition-colors">How it works</button>
            <button onClick={() => scrollTo(personaRef)} className="text-sm font-semibold text-slate-700 hover:text-indigo-600 transition-colors">Who it's for</button>
            <button onClick={() => navigate('/register')} className="text-sm font-semibold text-slate-700 hover:text-indigo-600 transition-colors">For employers</button>
            <button onClick={() => scrollTo(faqRef)} className="text-sm font-semibold text-slate-700 hover:text-indigo-600 transition-colors">FAQ</button>
            <button onClick={openContact}
              className="text-sm font-bold text-white rounded-xl px-4 py-2 transition-opacity hover:opacity-90"
              style={{ background: 'linear-gradient(135deg, #6366F1, #22D3EE)' }}>
              Contact
            </button>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative" ref={loginRef}>
              <button onClick={() => setLoginOpen(o => !o)}
                className="text-sm font-medium text-slate-700 border border-slate-200 rounded-xl px-4 py-2
                           hover:bg-slate-50 flex items-center gap-1.5">
                Login
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              {loginOpen && (
                <div className="absolute right-0 mt-2 w-64 bg-white border border-slate-200 rounded-2xl shadow-xl py-2 overflow-hidden">
                  <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider px-3 pb-1 pt-1">Sign in as</p>

                  {/* Employee — primary audience */}
                  <button onClick={() => navigate('/emp/login')}
                    className="w-full px-4 py-2.5 text-left hover:bg-sky-50 flex items-center gap-3 border-b border-slate-100">
                    <div className="w-7 h-7 rounded-lg bg-sky-100 flex items-center justify-center">
                      <span className="text-sky-600 text-xs">👤</span>
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-800">Employee</p>
                      <p className="text-[10px] text-slate-400">Access your career vault</p>
                    </div>
                  </button>

                  <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider px-3 pt-2 pb-1">Employer / Admin</p>
                  <button onClick={() => navigate('/org/login')}
                    className="w-full px-4 py-2.5 text-left hover:bg-slate-50 flex items-center gap-3">
                    <div className="w-7 h-7 rounded-lg bg-violet-100 flex items-center justify-center">
                      <span className="text-violet-600 text-xs font-bold">OA</span>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-800">Organisation user</p>
                      <p className="text-[10px] text-slate-400">OA Admin / CHRO / CFO / CISO</p>
                    </div>
                  </button>
                  <button onClick={() => navigate('/admin/login')}
                    className="w-full px-4 py-2.5 text-left hover:bg-slate-50 flex items-center gap-3">
                    <div className="w-7 h-7 rounded-lg bg-amber-100 flex items-center justify-center">
                      <span className="text-amber-600 text-xs font-bold">PA</span>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-800">Platform Admin</p>
                      <p className="text-[10px] text-slate-400">@prana.in accounts only</p>
                    </div>
                  </button>
                </div>
              )}
            </div>
            <GradBtn onClick={() => navigate('/register')} className="!px-5 !py-2 !text-sm hidden sm:block">
              Register your org →
            </GradBtn>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="max-w-6xl mx-auto px-6 pt-8 pb-12 text-center">
        <div className="inline-flex items-center gap-2 bg-indigo-50 border border-indigo-100 rounded-full px-4 py-1.5 mb-6">
          <span className="text-[10px] font-bold tracking-widest text-indigo-500 uppercase">Now live</span>
          <span className="text-[10px] text-indigo-400">Enterprise pilot-ready · DPDP Act 2023 compliant</span>
        </div>

        <h1 className="text-5xl sm:text-7xl font-extrabold text-slate-900 leading-[1.0] mb-6 tracking-tight">
          One vault. <GradText>Every employer.</GradText> Forever yours.
        </h1>

        <p className="text-slate-500 text-lg max-w-2xl mx-auto leading-relaxed mb-8">
          PRANA gives every Indian worker a permanent, portable career document vault — salary slips,
          Form 16, offer letters — pushed by employers, encrypted per-employee, owned entirely by you,
          and shareable in seconds with cryptographic proof of authenticity.
        </p>

        {/* Persona quick-links — pill cards */}
        <div className="flex flex-wrap justify-center gap-3 mb-8">
          {[
            { id: 'employee', label: 'Employees',     sub: 'One vault across your entire career',        color: '#0EA5E9', bg: '#F0F9FF', border: '#BAE6FD' },
            { id: 'chro',     label: 'CHRO / HR',     sub: 'Vault health & compliance intelligence',     color: '#10B981', bg: '#ECFDF5', border: '#A7F3D0' },
            { id: 'cfo',      label: 'CFO / Finance', sub: 'Aggregate payroll analytics',                color: '#6366F1', bg: '#EEF2FF', border: '#C7D2FE' },
            { id: 'ciso',     label: 'Infosec / DPO', sub: 'Trust architecture, not policy',            color: '#EF4444', bg: '#FEF2F2', border: '#FECACA' },
          ].map(p => (
            <button key={p.id}
              onClick={() => { setPersona(p.id); scrollTo(personaRef) }}
              className="flex flex-col items-start px-4 py-3 rounded-2xl border text-left transition-all hover:shadow-md hover:-translate-y-0.5"
              style={{ background: p.bg, borderColor: p.border }}>
              <span className="text-xs font-bold mb-0.5" style={{ color: p.color }}>{p.label}</span>
              <span className="text-[11px] text-slate-500">{p.sub}</span>
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center justify-center gap-3 mb-12">
          <GradBtn onClick={() => navigate('/register')} className="!px-8 !py-3.5 !text-base">
            Register your organisation →
          </GradBtn>
        </div>

        {/* Trust strip */}
        <div className="flex flex-wrap items-center justify-center gap-6 py-5 border-y border-slate-100">
          {TRUST_STATS.map(s => (
            <div key={s.value} className="text-center">
              <div className="font-extrabold text-xl"
                style={{ background: GRAD, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
                {s.value}
              </div>
              <div className="text-xs text-slate-400 mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Flow strip ── */}
      <section className="bg-slate-50 border-y border-slate-100 py-8 px-6">
        <div className="max-w-5xl mx-auto">
          <p className="text-center text-xs font-semibold text-slate-400 uppercase tracking-widest mb-6">
            From employer push to verified share — one continuous chain
          </p>
          <div className="flex items-center justify-center gap-3 flex-wrap">
            {[
              { icon: '🏢', label: 'Employer pushes', sub: 'Salary slips, Form 16, letters' },
              { icon: '🗄', label: 'PRANA vault',      sub: 'Encrypted, DEK per employee' },
              { icon: '↗',  label: 'You share',        sub: 'Watermarked, time-limited' },
              { icon: '✓',  label: 'Recipient verifies', sub: 'Bank scans QR. Document proves itself.' },
            ].map((n, i, arr) => (
              <div key={i} className="flex items-center gap-3">
                <div className="bg-white border border-slate-200 rounded-2xl px-5 py-4 text-center min-w-[130px]">
                  <div className="text-2xl mb-2">{n.icon}</div>
                  <div className="text-xs font-semibold text-slate-800">{n.label}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">{n.sub}</div>
                </div>
                {i < arr.length - 1 && <span style={{ color: '#CBD5E1', fontSize: 22 }}>→</span>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section ref={hiwRef} className="max-w-6xl mx-auto px-6 pt-14 pb-10">
        <div className="text-center mb-12">
          <p className="text-xs font-bold text-indigo-500 tracking-widest uppercase mb-3">How it works</p>
          <h2 className="text-4xl font-extrabold text-slate-900 mb-3">
            Six steps, <GradText>fully automated</GradText>
          </h2>
          <p className="text-slate-500 text-base max-w-md mx-auto">
            From first document push to verified share. PRANA handles everything in between.
          </p>
        </div>

        <div className="flex justify-center gap-2 mb-8">
          {HIW_STEPS.map((_, i) => (
            <button key={i} onClick={() => setActiveStep(i)}
              className={`h-1.5 rounded-full transition-all duration-300 ${i === activeStep ? 'w-8' : 'w-2 bg-slate-200'}`}
              style={i === activeStep ? { background: GRAD, width: 32 } : {}} />
          ))}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-10">
          {HIW_STEPS.map((s, i) => {
            const isActive = i === activeStep
            return (
              <div key={i}
                onClick={() => setActiveStep(i)}
                onMouseEnter={() => setHoveredStep(i)}
                onMouseLeave={() => setHoveredStep(null)}
                className="rounded-2xl border p-5 cursor-pointer transition-all duration-300"
                style={isActive || hoveredStep === i
                  ? { borderColor: '#C7D2FE', background: 'linear-gradient(135deg, #EEF2FF 0%, #F0FDFA 100%)', boxShadow: '0 4px 16px rgba(99,102,241,0.14)' }
                  : { borderColor: '#E2E8F0', background: '#F8FAFC' }}>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0 transition-all duration-200"
                    style={isActive || hoveredStep === i ? { background: GRAD, color: '#fff' } : { background: '#CBD5E1', color: '#64748B' }}>
                    {s.n}
                  </div>
                  <span className="text-xl">{s.icon}</span>
                </div>
                <h3 className={`font-semibold text-sm mb-1.5 transition-colors ${isActive || hoveredStep === i ? 'text-slate-900' : 'text-slate-600'}`}>{s.title}</h3>
                <p className="text-xs text-slate-400 leading-relaxed">{s.desc}</p>
              </div>
            )
          })}
        </div>

        {/* 3 perspective video placeholders */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-4xl mx-auto">
          {[
            { label: 'For CHROs', sublabel: 'Vault health · compliance · zero manual work', color: '#6366F1', glow: '#6366F1' },
            { label: 'For InfoSec', sublabel: 'Audit trail · access control · anomaly alerts', color: '#0EA5E9', glow: '#22D3EE' },
            { label: 'For Employees', sublabel: 'Own your docs · share securely · ask PRANA', color: '#10B981', glow: '#10B981' },
          ].map(v => (
            <div key={v.label} className="bg-slate-900 rounded-2xl overflow-hidden border border-slate-700 aspect-video
                            flex flex-col items-center justify-center gap-3 relative cursor-pointer group">
              <div className="absolute inset-0 opacity-20 group-hover:opacity-30 transition-opacity"
                style={{ background: `radial-gradient(circle at 50% 50%, ${v.glow}, transparent 70%)` }} />
              <div className="relative z-10 flex flex-col items-center gap-2 px-4 text-center">
                <div className="w-11 h-11 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform"
                  style={{ background: v.color }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="white"><path d="M8 5v14l11-7z"/></svg>
                </div>
                <p className="text-white text-xs font-semibold">{v.label}</p>
                <p className="text-slate-400 text-[10px] leading-relaxed">{v.sublabel}</p>
                <span className="text-[9px] font-medium px-2 py-0.5 rounded-full mt-1"
                  style={{ background: `${v.color}22`, color: v.color }}>60 sec · coming soon</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Persona tabs: Employee / CHRO / CFO / CISO ── */}
      <section ref={personaRef} className="bg-slate-50 border-y border-slate-100 pt-12 pb-16 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-10">
            <p className="text-xs font-bold text-indigo-500 tracking-widest uppercase mb-3">Who it's for</p>
            <h2 className="text-4xl font-extrabold text-slate-900">
              <GradText>Built for everyone</GradText> in the document chain
            </h2>
          </div>

          {/* Persona selector tabs */}
          <div className="flex flex-wrap justify-center gap-2 mb-8">
            {PERSONAS.map(p => (
              <button key={p.id} onClick={() => setPersona(p.id)}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold
                            transition-all border ${persona === p.id
                              ? 'text-white border-transparent shadow-sm'
                              : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'}`}
                style={persona === p.id ? { background: p.color } : {}}>
                {p.icon} {p.label}
              </button>
            ))}
          </div>

          {/* ── Employee ── */}
          {persona === 'employee' && (
            <div>
              <div className="text-center mb-6">
                <h3 className="text-2xl font-bold text-slate-900 mb-2">Your vault. Your rules. Always.</h3>
                <p className="text-slate-500 text-sm max-w-xl mx-auto">
                  Every employer you work for pushes documents to the same permanent vault.
                  No more chasing HR. Share in seconds with cryptographic proof that banks, recruiters, and agencies trust.
                </p>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
                {EMPLOYEE_FEATURES.map(f => (
                  <div key={f.title}
                    className="bg-white rounded-2xl border border-slate-100 p-4 cursor-default
                               transition-all duration-200
                               hover:shadow-lg hover:-translate-y-1 hover:border-transparent"
                    style={{ borderTopColor: f.accent, borderTopWidth: 3 }}
                    onMouseEnter={e => {
                      const el = e.currentTarget
                      el.style.boxShadow = `0 8px 24px ${f.accent}28`
                      el.style.borderColor = f.accent
                    }}
                    onMouseLeave={e => {
                      const el = e.currentTarget
                      el.style.boxShadow = ''
                      el.style.borderColor = ''
                      el.style.borderTopColor = f.accent
                      el.style.borderTopWidth = '3px'
                    }}>
                    <div className="flex items-center gap-2.5 mb-2.5">
                      <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg flex-shrink-0
                                      transition-transform duration-200 hover:scale-110"
                        style={{ background: f.bg }}>
                        {f.icon}
                      </div>
                      <h4 className="font-bold text-slate-900 text-sm leading-tight">{f.title}</h4>
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed font-medium">{f.desc}</p>
                  </div>
                ))}
              </div>
              <div className="bg-sky-50 border border-sky-100 rounded-2xl p-5 flex items-start gap-4">
                <span className="text-2xl">💬</span>
                <div>
                  <p className="text-sm font-semibold text-slate-800 mb-1">Ask PRANA — AI Vault Assistant</p>
                  <p className="text-sm text-slate-500">
                    "What was my salary in March 2022?" Natural language queries on your own verified documents.
                    Answers derived from insights only — raw figures never leave your encrypted vault.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ── CHRO ── */}
          {persona === 'chro' && (
            <div>
              <div className="text-center mb-6">
                <h3 className="text-2xl font-bold text-slate-900 mb-2">People intelligence from verified documents.</h3>
                <p className="text-slate-500 text-sm max-w-xl mx-auto">
                  Stop chasing employees for documents. PRANA tells you exactly which vault is incomplete,
                  which compliance deadline is coming, and which documents are missing — before they become audit findings.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4 mb-5">
                {CHRO_FEATURES.map(f => (
                  <div key={f.title} className="bg-white rounded-2xl border border-slate-100 p-5 hover:shadow-sm transition-shadow">
                    <div className="text-2xl mb-3">{f.icon}</div>
                    <h4 className="font-semibold text-slate-800 text-sm mb-1">{f.title}</h4>
                    <p className="text-xs text-slate-400 leading-relaxed">{f.desc}</p>
                  </div>
                ))}
              </div>
              <div className="bg-emerald-50 border border-emerald-100 rounded-2xl p-5 grid grid-cols-3 gap-4 text-center">
                {[
                  { v: '87%', l: 'Vault completeness (sample)' },
                  { v: '500', l: 'Active employees tracked' },
                  { v: '63',  l: 'Incomplete vaults flagged' },
                ].map(s => (
                  <div key={s.l}>
                    <div className="text-2xl font-extrabold text-emerald-700">{s.v}</div>
                    <div className="text-xs text-emerald-600">{s.l}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── CFO ── */}
          {persona === 'cfo' && (
            <div>
              <div className="text-center mb-6">
                <h3 className="text-2xl font-bold text-slate-900 mb-2">Aggregate payroll intelligence. No individual salary ever visible.</h3>
                <p className="text-slate-500 text-sm max-w-xl mx-auto">
                  Every figure is aggregated across a minimum of <strong>30 consenting employees</strong>.
                  Source: AI-extracted fields from employer-pushed salary slips — not self-reported data.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4 mb-5">
                {CFO_FEATURES.map(f => (
                  <div key={f.title} className="bg-white rounded-2xl border border-slate-100 p-5 hover:shadow-sm transition-shadow">
                    <div className="text-2xl mb-3">{f.icon}</div>
                    <h4 className="font-semibold text-slate-800 text-sm mb-1">{f.title}</h4>
                    <p className="text-xs text-slate-400 leading-relaxed">{f.desc}</p>
                  </div>
                ))}
              </div>
              <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-5 flex items-start gap-3">
                <span className="text-xl mt-0.5">🔒</span>
                <div>
                  <p className="text-sm font-semibold text-indigo-800 mb-1">Consent-first. Always.</p>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    All intelligence is derived exclusively from employees who have opted in to anonymous data sharing in their vault Settings.
                    487 of 500 employees (97.4%) consented in a reference deployment. Aggregates surface only when cohort ≥ 30.
                    Individual values are never shown, never derivable.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ── CISO / Infosec ── */}
          {persona === 'ciso' && (
            <div>
              <div className="text-center mb-6">
                <h3 className="text-2xl font-bold text-slate-900 mb-2">Not policy. Architecture.</h3>
                <p className="text-slate-500 text-sm max-w-xl mx-auto">
                  Misuse is structurally impossible. Controls fail when credentials are compromised.
                  PRANA's architecture prevents misuse regardless of who has the keys.
                </p>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
                {CISO_STATS.map(s => (
                  <div key={s.value} className="bg-white border border-red-100 rounded-2xl p-4 text-center">
                    <div className="text-2xl font-extrabold text-red-600 mb-1">{s.value}</div>
                    <div className="text-[10px] text-slate-400 leading-tight">{s.label}</div>
                  </div>
                ))}
              </div>

              <div className="space-y-2 mb-5">
                {CISO_LAYERS.map((l, i) => (
                  <div key={i} className="bg-white rounded-2xl border border-slate-100 px-5 py-4 flex items-start gap-4">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-extrabold flex-shrink-0"
                      style={{ background: GRAD }}>
                      {l.n}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="text-[10px] font-bold text-red-500 bg-red-50 border border-red-100 rounded-full px-2 py-0.5">
                          {l.label}
                        </span>
                        <span className="text-sm font-semibold text-slate-800">{l.title}</span>
                      </div>
                      <p className="text-xs text-slate-400 leading-relaxed">{l.desc}</p>
                    </div>
                  </div>
                ))}
              </div>

              <div className="bg-slate-900 rounded-2xl p-5 border-l-4 border-l-red-500">
                <p className="text-slate-300 text-sm italic">
                  "We built the system so that even we cannot misuse your data. The Portal Admin cannot read a single document —
                  not because of a policy, but because the database refuses the query."
                </p>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ── Trust Architecture (universal) ── */}
      <section className="bg-slate-900 py-16 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-10">
            <p className="text-xs font-bold text-indigo-400 tracking-widest uppercase mb-3">Security by design</p>
            <h2 className="text-3xl font-extrabold text-white mb-3">
              7-layer trust architecture — <span style={{ background: GRAD, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>applies to everyone</span>
            </h2>
            <p className="text-slate-400 text-sm max-w-xl mx-auto">
              Misuse is structurally impossible. These controls work regardless of who has the credentials —
              employer, admin, or PRANA itself.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 gap-3 mb-8">
            {CISO_LAYERS.map((l) => (
              <div key={l.n} className="flex items-start gap-4 bg-white/5 border border-white/10 rounded-2xl px-5 py-4">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-extrabold flex-shrink-0"
                  style={{ background: GRAD }}>
                  {l.n}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-[10px] font-bold rounded-full px-2 py-0.5" style={{ color: '#818CF8', background: 'rgba(99,102,241,0.15)' }}>
                      {l.label}
                    </span>
                    <span className="text-sm font-semibold text-white">{l.title}</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">{l.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
            {CISO_STATS.map(s => (
              <div key={s.value} className="bg-white/5 border border-white/10 rounded-2xl p-4 text-center">
                <div className="text-2xl font-extrabold mb-1"
                  style={{ background: GRAD, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
                  {s.value}
                </div>
                <div className="text-[10px] text-slate-400 leading-tight">{s.label}</div>
              </div>
            ))}
          </div>

          <div className="border-l-4 border-l-indigo-500 bg-white/5 rounded-r-2xl px-6 py-4">
            <p className="text-slate-300 text-sm italic">
              "We built the system so that even we cannot misuse your data. The Portal Admin cannot read a single document —
              not because of a policy, but because the database refuses the query."
            </p>
            <p className="text-indigo-400 text-xs mt-2 font-semibold">— PRANA Architecture Principle</p>
          </div>
        </div>
      </section>

      {/* ── What's Live + What's Coming ── */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <div className="text-center mb-10">
          <p className="text-xs font-bold text-indigo-500 tracking-widest uppercase mb-3">Product roadmap</p>
          <h2 className="text-3xl font-extrabold text-slate-900 mb-3">
            <GradText>Live today.</GradText> What's coming next.
          </h2>
          <p className="text-slate-400 text-sm max-w-lg mx-auto">
            The core vault, AI pipeline, mobile app, HRMS integration, and chatbot are all live.
            What follows makes it extraordinary.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-6">
          {/* Phase I */}
          <div className="rounded-3xl border-2 border-emerald-200 bg-emerald-50/40 p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-xl bg-emerald-500 flex items-center justify-center">
                <span className="text-white text-sm font-bold">✓</span>
              </div>
              <div>
                <p className="font-bold text-slate-900 text-base">Live Now</p>
                <p className="text-xs text-emerald-600">Enterprise pilot-ready · DPDP Act 2023 compliant</p>
              </div>
            </div>
            <div className="space-y-2.5">
              {[
                { icon: '🗄',  label: 'My Vault',                sub: 'All documents, all employers, one place' },
                { icon: '↗',  label: 'C-Share',                  sub: 'Cryptographic verification. Bank scans QR.' },
                { icon: '📱',  label: 'Native Mobile App',        sub: 'React Native / Expo. iOS and Android.' },
                { icon: '💬',  label: 'Ask PRANA (AI chatbot)',   sub: 'Natural language queries on your own vault.' },
                { icon: '🔗',  label: 'HRMS Integration',         sub: 'Darwinbox + Keka. Pull, push, webhook.' },
                { icon: '🏆',  label: 'Career Score + Gamification', sub: '0–100 score, streaks, badges.' },
                { icon: '📋',  label: 'Activity Log',             sub: 'Every access, push, and share event' },
                { icon: '🔔',  label: 'Smart Alerts',             sub: 'Proactive, not passive' },
                { icon: '⚖',  label: 'DPDP Rights Centre',       sub: 'All 6 rights, properly implemented' },
                { icon: '📅',  label: 'Career Timeline',          sub: 'AI-built from verified documents' },
                { icon: '📊',  label: 'Vault Health Score',       sub: 'Document completeness %' },
                { icon: '📦',  label: 'Share Bundles',            sub: 'Loan, BGV, visa — one link' },
                { icon: '📨',  label: 'Document Request Flow',    sub: 'Ask your employer for missing docs' },
                { icon: '🔍',  label: 'Privacy Cockpit',          sub: 'DPDP S.11 — every field, every access' },
                { icon: '⬆',  label: 'Bulk Upload + AI Screen',  sub: 'Content policy, contamination detection' },
                { icon: '📊',  label: 'CHRO Vault Dashboard',     sub: 'Completeness, compliance calendar, digest' },
                { icon: '💰',  label: 'CFO Payroll Intelligence', sub: 'Aggregate only. Consent-based. ≥30 cohort' },
              ].map(f => (
                <div key={f.label} className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-emerald-100 border border-emerald-300 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-emerald-600 text-[9px] font-bold">✓</span>
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-slate-800">{f.icon} {f.label}</span>
                    <span className="text-[10px] text-slate-400 ml-1.5">{f.sub}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Phase II */}
          <div className="rounded-3xl border-2 border-indigo-100 bg-indigo-50/30 p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: GRAD }}>
                <span className="text-white text-sm font-bold">→</span>
              </div>
              <div>
                <p className="font-bold text-slate-900 text-base">Coming Next</p>
                <p className="text-xs text-indigo-500">The vault works without these. They make it extraordinary.</p>
              </div>
            </div>
            <div className="space-y-2.5">
              {[
                { icon: "\u{1FAAA}", label: "Career Passport",              sub: "One public link. Recruiter scans QR — verified instantly.",           tag: "Employee"  },
                { icon: "🔎",        label: "Employer Intelligence",        sub: "Slip says Engineer. Letter says Senior Engineer. PRANA catches it.",   tag: "Employee"  },
                { icon: "🧾",        label: "Tax Document Organiser",       sub: "Gross income, total TDS, annual summary. Ready for your CA.",            tag: "Employee"  },
                { icon: "🤝",        label: "Gig Worker Mode",              sub: "50M+ gig workers. Self-upload + AI extraction + career record.",          tag: "Employee"  },
                { icon: "📈",        label: "Full Salary Benchmarking",     sub: "Verified cross-org bands. Needs 50+ orgs. Consent-based.",                tag: "CFO"       },
                { icon: "🤖",        label: "CHRO AI Assistant",            sub: "What is our Form-16 issuance rate for Q2? — answered instantly.",        tag: "CHRO"      },
                { icon: "💬",        label: "WhatsApp + DigiLocker + EPFO", sub: "India-first channels. Government API linkage.",                           tag: "Platform"  },
                { icon: "🔗",        label: "Third-party Verification API", sub: "Banks, NBFCs, BGV firms. Replaces the phone call to HR.",                 tag: "Platform"  },
              ].map(f => (
                <div key={f.label} className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-indigo-100 border border-indigo-200 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-indigo-400 text-[9px] font-bold">→</span>
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-slate-800">{f.icon} {f.label}</span>
                    <span className="text-[9px] font-bold text-indigo-400 bg-indigo-100 rounded-full px-1.5 py-0.5 ml-1.5">{f.tag}</span>
                    <p className="text-[10px] text-slate-400 mt-0.5 leading-relaxed">{f.sub}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── For Organisations ── */}
      <section className="max-w-6xl mx-auto px-6 pt-10 pb-16">
        <div className="text-center mb-10">
          <p className="text-xs font-bold text-indigo-500 tracking-widest uppercase mb-3">For organisations</p>
          <h2 className="text-4xl font-extrabold text-slate-900">
            Every role in your org, <GradText>covered</GradText>
          </h2>
          <p className="text-slate-400 text-sm mt-3 max-w-lg mx-auto">
            Onboard in 15 minutes. No IT integration required to start. HRMS API available for automated pushes.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 gap-4 mb-8">
          {ORG_FEATURES.map(f => (
            <div key={f.title} className="bg-slate-50 border border-slate-100 rounded-2xl p-5 flex items-start gap-4">
              <div className="text-2xl">{f.icon}</div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h4 className="font-semibold text-slate-800 text-sm">{f.title}</h4>
                  <span className="text-[10px] font-bold text-slate-400 bg-white border border-slate-200 rounded-full px-2 py-0.5">
                    {f.role}
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="grid sm:grid-cols-2 gap-6">
          <div className="bg-white rounded-3xl border border-slate-200 p-8">
            <div className="w-12 h-12 rounded-2xl bg-indigo-100 flex items-center justify-center text-2xl mb-5">🏢</div>
            <h3 className="text-xl font-bold text-slate-900 mb-2">Register your organisation</h3>
            <p className="text-slate-500 text-sm leading-relaxed mb-6">
              Push salary slips, Form 16, and HR letters to employee vaults automatically.
              Connects via portal upload or HRMS API. Onboard in 15 minutes.
            </p>
            <GradBtn onClick={() => navigate('/register')} className="w-full !py-3 !rounded-xl">
              Register now →
            </GradBtn>
          </div>
          <div className="bg-white rounded-3xl border border-slate-200 p-8">
            <div className="w-12 h-12 rounded-2xl bg-sky-100 flex items-center justify-center text-2xl mb-5">📱</div>
            <h3 className="text-xl font-bold text-slate-900 mb-2">For employees</h3>
            <p className="text-slate-500 text-sm leading-relaxed mb-6">
              Your vault activates the moment your employer joins PRANA and pushes your first document.
              Access your career vault on the web or download the PRANA mobile app.
            </p>
            <div className="flex flex-col gap-2">
              <GradBtn onClick={() => navigate('/emp/login')} className="w-full !py-3 !rounded-xl">
                Access your vault →
              </GradBtn>
              <button className="w-full border border-slate-200 text-slate-600 font-semibold rounded-xl py-2.5 text-sm hover:bg-slate-50 transition-colors">
                Download the PRANA app
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Privacy promise dark section ── */}
      <section className="bg-slate-900 py-16 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="w-14 h-14 rounded-2xl mx-auto mb-6 flex items-center justify-center text-3xl"
            style={{ background: GRAD }}>🔒</div>
          <h2 className="text-3xl font-extrabold text-white mb-3">Privacy by design. Not by policy.</h2>
          <p className="text-slate-500 text-sm mb-10">
            Non-negotiable. Structural. Cannot be switched off by any administrator.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { icon: '🔐', title: 'Zero Raw ₹ Stored',         desc: 'Salary figures never enter our database. AI extracts insights only — not values.' },
              { icon: '🛡', title: 'Per-Employee Encryption',    desc: 'Every person has their own encryption key. One breach = one person. Never the org.' },
              { icon: '👁', title: 'Zero Platform Access',       desc: 'Platform Admin cannot read a single document. The database refuses the query.' },
              { icon: '📜', title: 'Immutable Audit Event',      desc: 'Every access is logged forever. No UPDATE or DELETE on audit records. Ever.' },
              { icon: '🔏', title: 'Format-Preserving PAN',      desc: 'PAN is tokenised in 2ms and destroyed. No row links your PAN to your name.' },
              { icon: '🇮🇳', title: 'DPDP Act 2023 Compliant',  desc: 'All 6 data principal rights implemented. Consent, Erasure, Grievance, Nomination.' },
              { icon: '📅', title: '7-Year Audit Retention',     desc: 'Regulatory-grade audit trail. Hot storage for 2 years, cold archive for 7.' },
              { icon: '✍', title: 'Consent-First Always',        desc: 'No document reaches an employer dashboard unless the employee has explicitly consented.' },
            ].map(f => (
              <div key={f.title}
                className="bg-white/5 border border-white/10 rounded-2xl p-4 text-left
                           hover:bg-white/10 hover:border-white/20 transition-all duration-200 group">
                <div className="text-2xl mb-3 group-hover:scale-110 transition-transform duration-200 inline-block">{f.icon}</div>
                <p className="text-white font-bold text-sm mb-1.5">{f.title}</p>
                <p className="text-slate-400 text-xs leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <div ref={faqRef} className="bg-slate-50 border-t border-slate-100">
        <FaqSection />
      </div>

      <div ref={contactRef} />

      {/* ── Footer ── */}
      <footer className="bg-slate-950 text-slate-400 pt-14 pb-8 px-6">
        <div className="max-w-6xl mx-auto">
          {/* Top: brand + columns */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-10 mb-12">
            {/* Brand */}
            <div className="col-span-2 sm:col-span-1">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: GRAD }}>
                  <span className="text-white font-bold text-sm">P</span>
                </div>
                <span className="font-mono font-bold text-white text-lg tracking-tight">
                  PRANA<span className="text-indigo-400">·</span>
                </span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed mb-3">
                Personal Repository &amp; Networked Authentications
              </p>
              <p className="text-[11px] text-slate-600 leading-relaxed">
                Career document vault for every Indian worker. DPDP Act 2023 compliant.
              </p>
              <div className="flex gap-2 mt-4">
                <span className="text-[10px] bg-emerald-900/50 text-emerald-400 border border-emerald-800 rounded-full px-2.5 py-1 font-semibold">Live Now</span>
                <span className="text-[10px] bg-indigo-900/50 text-indigo-400 border border-indigo-800 rounded-full px-2.5 py-1 font-semibold">Pilot-Ready</span>
              </div>
            </div>

            {/* Product */}
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">Product</p>
              <ul className="space-y-2.5">
                {[
                  ['My Vault', '#'],
                  ['C-Share', '#'],
                  ['Career Timeline', '#'],
                  ['DPDP Rights Centre', '#'],
                  ['Vault Health Score', '#'],
                  ['Share Bundles', '#'],
                  ['Ask PRANA AI', '#'],
                ].map(([l, h]) => (
                  <li key={l}><a href={h} className="text-xs hover:text-white transition-colors">{l}</a></li>
                ))}
              </ul>
            </div>

            {/* For Organisations */}
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">For Organisations</p>
              <ul className="space-y-2.5">
                {[
                  ['Register your org', '/register'],
                  ['HRMS API integration', '#'],
                  ['CHRO Dashboard', '#'],
                  ['CFO Analytics', '#'],
                  ['CISO Security View', '#'],
                  ['Employee vault login', '/emp/login'],
                  ['OA Portal login', '/org/login'],
                  ['Platform Admin', '/admin/login'],
                ].map(([l, h]) => (
                  <li key={l}><a href={h} className="text-xs hover:text-white transition-colors">{l}</a></li>
                ))}
              </ul>
            </div>

            {/* Company */}
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">Company</p>
              <ul className="space-y-2.5">
                {[
                  ['About PRANA', '#'],
                  ['Security architecture', '/legal/privacy#security'],
                  ['DPDP compliance', '/legal/privacy#dpdp'],
                  ['Request a demo', '#'],
                  ['Blog', '#'],
                ].map(([l, h]) => (
                  <li key={l}><a href={h} className="text-xs hover:text-white transition-colors">{l}</a></li>
                ))}
              </ul>
            </div>

            {/* Legal */}
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">Legal</p>
              <ul className="space-y-2.5">
                {[
                  ['Privacy policy',            '/legal/privacy'],
                  ['Terms of use',              '/legal/terms'],
                  ['Data Processing Agreement', '/legal/dpa'],
                  ['Cookie policy',             '/legal/cookies'],
                  ['Grievance Redressal',       '/legal/grievance'],
                  ['API Terms',                 '/legal/api-terms'],
                ].map(([l, h]) => (
                  <li key={l}><a href={h} className="text-xs hover:text-white transition-colors">{l}</a></li>
                ))}
              </ul>
            </div>
          </div>

          {/* Divider */}
          <div className="border-t border-white/5 pt-6 flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-[11px] text-slate-600">© 2025 PRANA Technologies Pvt Ltd. All rights reserved. Built for India.</p>
            <div className="flex items-center gap-4">
              {['AES-256', 'DPDP 2023', 'AWS KMS', 'YugabyteDB'].map(t => (
                <span key={t} className="text-[10px] text-slate-600 border border-white/5 rounded px-2 py-0.5">{t}</span>
              ))}
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
