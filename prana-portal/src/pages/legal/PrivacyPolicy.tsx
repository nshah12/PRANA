import { LegalLayout } from '@/components/LegalLayout'

export function PrivacyPolicy() {
  return (
    <LegalLayout
      title="Privacy Policy"
      subtitle="How PRANA collects, uses, and protects your personal data — in plain language."
      badge="Legal · Privacy"
    >
      <p className="text-xs text-slate-400 mb-8">Last updated: June 2025 · Effective: June 2025 · DPDP Act 2023 compliant</p>

      <Section title="1. Who we are">
        <p>
          PRANA Technologies Pvt Ltd ("PRANA", "we", "us") operates a career document vault platform that
          enables Indian workers to receive, store, and share employment documents — salary slips, Form 16,
          offer letters, and other HR records — pushed by their employers.
        </p>
        <p>
          We are a Data Fiduciary under the Digital Personal Data Protection Act, 2023 (DPDP Act). Our
          registered office is in India and our infrastructure runs in AWS ap-south-1 (Mumbai) with a
          secondary region in ap-south-2 (Hyderabad).
        </p>
      </Section>

      <Section title="2. What data we collect">
        <p>We collect the minimum data necessary to provide the vault service:</p>
        <table className="w-full text-xs border-collapse mb-4">
          <thead>
            <tr className="bg-slate-100">
              <th className="text-left p-2 border border-slate-200 font-semibold">Category</th>
              <th className="text-left p-2 border border-slate-200 font-semibold">Examples</th>
              <th className="text-left p-2 border border-slate-200 font-semibold">Source</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Identity', 'Name, mobile number, corporate email', 'You / your employer'],
              ['Employment documents', 'Salary slips, Form 16, offer letters, relieving letters', 'Your employer via PRANA Portal or HRMS API'],
              ['AI-extracted insights', 'Employment band, tenure, document type — never raw ₹ or PAN', 'Our 6-stage AI pipeline'],
              ['Account data', 'Login email, TOTP secret (encrypted), session tokens', 'You'],
              ['Audit data', 'Access timestamps, share events, login attempts', 'System-generated'],
            ].map(([cat, ex, src]) => (
              <tr key={cat} className="border-b border-slate-100">
                <td className="p-2 border border-slate-200 font-medium">{cat}</td>
                <td className="p-2 border border-slate-200 text-slate-600">{ex}</td>
                <td className="p-2 border border-slate-200 text-slate-500">{src}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Callout color="amber">
          <strong>What we never store:</strong> Raw salary figures (₹), PAN numbers in plaintext, or any
          field that directly identifies financial position. Our AI extracts insights only — never raw values.
        </Callout>
      </Section>

      <Section title="3. How we use your data" id="use">
        <ul>
          <li><strong>Vault operation:</strong> Storing and retrieving your encrypted documents</li>
          <li><strong>Document sharing:</strong> Generating watermarked, time-limited share links (C-Share)</li>
          <li><strong>Career intelligence:</strong> Building your Career Timeline and Vault Health Score from AI-extracted insights</li>
          <li><strong>DPDP compliance:</strong> Processing your rights requests (access, correction, erasure, grievance)</li>
          <li><strong>Security:</strong> Detecting anomalies, preventing unauthorised access, maintaining audit logs</li>
          <li><strong>Communications:</strong> Alerts about documents arriving, shares expiring, or rights requests</li>
        </ul>
        <p>We do not sell your data, use it for advertising, or share it with third parties beyond what is described in this policy.</p>
      </Section>

      <Section title="4. Encryption and security" id="security">
        <p>Every document in PRANA is protected by a layered encryption model:</p>
        <ul>
          <li><strong>Per-employee DEK:</strong> Each employee has a unique Data Encryption Key. A colleague's key cannot decrypt your documents.</li>
          <li><strong>Tenant KEK:</strong> The DEK is envelope-encrypted with your employer's Key Encryption Key, stored in AWS KMS (ap-south-1, customer-managed).</li>
          <li><strong>AES-256-GCM</strong> at rest. TLS 1.3 in transit.</li>
          <li><strong>PAN tokenisation:</strong> PAN → HMAC-SHA256 in 2ms. Plaintext destroyed. No row in our database links your PAN to your name.</li>
          <li><strong>Zero access by PA:</strong> Portal Admin accounts cannot execute SELECT on document rows. Enforced at database level via PostgreSQL Row-Level Security (RLS) — not policy.</li>
        </ul>
      </Section>

      <Section title="5. Your DPDP rights" id="dpdp">
        <p>As a Data Principal under the DPDP Act 2023, you have the following rights, all accessible from your DPDP Rights Centre in the PRANA mobile app:</p>
        <ul>
          <li><strong>Right to Access:</strong> Download a copy of all personal data we hold about you</li>
          <li><strong>Right to Correction:</strong> Update inaccurate personal data</li>
          <li><strong>Right to Erasure:</strong> Request deletion of your account and all associated data</li>
          <li><strong>Right to Grievance:</strong> Raise a complaint and receive a response within 72 hours</li>
          <li><strong>Right to Nominate:</strong> Designate a nominee to exercise your rights in the event of incapacity or death</li>
          <li><strong>Consent management:</strong> Withdraw consent for optional data uses (analytics) at any time</li>
        </ul>
        <p>Requests are processed within 30 days. Erasure requests trigger a <code>DataErasureWorkflow</code> that permanently deletes all vault data, share tokens, and audit entries that identify you.</p>
      </Section>

      <Section title="6. Data retention">
        <ul>
          <li><strong>Documents:</strong> Retained as long as your account is active. Deleted on erasure request.</li>
          <li><strong>Audit logs:</strong> 7 years (regulatory requirement). Stored in YugabyteDB (hot, 0–2 years) and Apache Iceberg on S3 (cold, 2–7 years). Immutable — no UPDATE or DELETE permitted on <code>audit_event</code>.</li>
          <li><strong>Share tokens:</strong> Automatically expired per your setting. Deleted after expiry.</li>
          <li><strong>OTP and session data:</strong> Deleted on use or after 10 minutes, whichever is earlier.</li>
        </ul>
      </Section>

      <Section title="7. Cookies">
        <p>
          PRANA uses only essential cookies: session authentication (httpOnly, Secure, SameSite=Strict) and
          CSRF protection tokens. We do not use tracking, analytics, or advertising cookies. See our{' '}
          <a href="/legal/cookies" className="text-indigo-600 hover:underline">Cookie Policy</a> for full details.
        </p>
      </Section>

      <Section title="8. Contact our Data Protection Officer">
        <p>
          For any privacy-related queries or to exercise your rights, contact our DPO at{' '}
          <a href="mailto:dpo@prana.in" className="text-indigo-600 hover:underline">dpo@prana.in</a>.
          For escalated grievances, use the Grievance Redressal process described in our{' '}
          <a href="/legal/grievance" className="text-indigo-600 hover:underline">Grievance Redressal Policy</a>.
        </p>
      </Section>
    </LegalLayout>
  )
}

function Section({ title, id, children }: { title: string; id?: string; children: React.ReactNode }) {
  return (
    <section id={id} className="mb-8">
      <h2 className="text-lg font-bold text-slate-900 mb-3 pb-2 border-b border-slate-100">{title}</h2>
      <div className="space-y-3 text-sm text-slate-600 leading-relaxed">{children}</div>
    </section>
  )
}

function Callout({ color, children }: { color: 'amber' | 'indigo' | 'emerald'; children: React.ReactNode }) {
  const cls = {
    amber:  'bg-amber-50 border-amber-200 text-amber-800',
    indigo: 'bg-indigo-50 border-indigo-200 text-indigo-800',
    emerald:'bg-emerald-50 border-emerald-200 text-emerald-800',
  }[color]
  return <div className={`border rounded-xl px-4 py-3 text-xs leading-relaxed ${cls}`}>{children}</div>
}
