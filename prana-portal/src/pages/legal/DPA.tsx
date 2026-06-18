import { LegalLayout } from '@/components/LegalLayout'

export function DPA() {
  return (
    <LegalLayout
      title="Data Processing Agreement"
      subtitle="The contractual framework governing how PRANA processes personal data on behalf of your organisation."
      badge="Legal · DPA"
    >
      <p className="text-xs text-slate-400 mb-8">
        Last updated: June 2025 · This DPA is incorporated by reference into the PRANA Master Subscription Agreement.
        It applies to all organisations (Data Fiduciaries) that have onboarded on the PRANA platform.
      </p>

      <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 mb-8 text-xs text-indigo-800 leading-relaxed">
        <strong>Role clarification under DPDP Act 2023:</strong> Your organisation is the <strong>Data Fiduciary</strong> that
        determines the purpose and means of processing your employees' personal data. PRANA acts as a
        <strong> Data Processor</strong> when processing that data on your behalf. Employees are the <strong>Data Principals</strong>.
        This DPA governs the relationship between your organisation and PRANA in that capacity.
      </div>

      <Section title="1. Definitions">
        <Def term="Data Fiduciary">The organisation (employer) that has onboarded on PRANA and determines the purpose and means of processing employees' personal data.</Def>
        <Def term="Data Processor">PRANA Technologies Pvt Ltd, acting on the instructions of the Data Fiduciary.</Def>
        <Def term="Data Principal">The employee whose personal data is being processed (salary slips, Form 16, offer letters, and AI-extracted insights).</Def>
        <Def term="Personal Data">Any data that can identify a natural person — including names, email addresses, PAN (in encrypted/tokenised form), employment history, and document metadata.</Def>
        <Def term="Sensitive Personal Data">PAN (format-preserving encrypted), TOTP secrets (AES-256-GCM encrypted), and biometric identifiers if applicable.</Def>
      </Section>

      <Section title="2. Scope of processing">
        <p>PRANA processes personal data on behalf of the Data Fiduciary for the following purposes only:</p>
        <ul>
          <li>Receiving, encrypting, and storing employment documents pushed via the PRANA Portal or HRMS API</li>
          <li>Running the 6-stage AI pipeline to extract career insights (never raw salary figures)</li>
          <li>Enabling employees to access, share, and manage their vaulted documents</li>
          <li>Generating compliance dashboards and analytics for CHRO, CFO, and Infosec roles</li>
          <li>Maintaining the immutable audit log for the statutory 7-year period</li>
        </ul>
        <p>PRANA will not process personal data for any other purpose without prior written instruction from the Data Fiduciary.</p>
      </Section>

      <Section title="3. Data Fiduciary obligations">
        <p>By onboarding on PRANA, the Data Fiduciary agrees to:</p>
        <ul>
          <li>Obtain valid, documented consent from each employee (Data Principal) before pushing their documents to PRANA</li>
          <li>Maintain a consent register and make it available to PRANA on request</li>
          <li>Ensure that documents pushed to PRANA are authentic and belong to the identified employee</li>
          <li>Promptly inform PRANA if an employee withdraws consent or requests data erasure</li>
          <li>Implement access controls so that only authorised OA-Operators, OA-Admins, CHRO, CFO, and Infosec personnel access the PRANA Portal</li>
        </ul>
      </Section>

      <Section title="4. PRANA's obligations as Data Processor">
        <p>PRANA commits to:</p>
        <ul>
          <li><strong>Process only on instruction:</strong> Process personal data solely as instructed by the Data Fiduciary and as described in this DPA.</li>
          <li><strong>Confidentiality:</strong> Ensure all personnel with access to personal data are bound by confidentiality obligations.</li>
          <li><strong>Security:</strong> Maintain AES-256 encryption at rest, TLS 1.3 in transit, per-employee DEK/KEK envelope encryption, and row-level security controls. See our <a href="/legal/privacy#security" className="text-indigo-600 hover:underline">Security Architecture</a>.</li>
          <li><strong>Sub-processors:</strong> Use only approved sub-processors (AWS for infrastructure and KMS, Apache Iceberg/S3 for cold audit storage). We will notify you 30 days before adding new sub-processors.</li>
          <li><strong>Rights assistance:</strong> Assist the Data Fiduciary in responding to Data Principal rights requests (access, correction, erasure, grievance) within the statutory timelines.</li>
          <li><strong>Breach notification:</strong> Notify the Data Fiduciary within 72 hours of discovering a personal data breach that affects their employees' data.</li>
          <li><strong>Deletion on termination:</strong> Delete all personal data belonging to the Data Fiduciary's employees within 30 days of contract termination, except audit logs retained per statutory obligation.</li>
        </ul>
      </Section>

      <Section title="5. Encryption architecture">
        <p>PRANA's encryption model is designed so that no single party has unrestricted access:</p>
        <ul>
          <li><strong>Per-employee DEK:</strong> Each employee's documents are encrypted with a unique Data Encryption Key. DEK compromise affects only one person.</li>
          <li><strong>Tenant KEK:</strong> The DEK is envelope-encrypted with the organisation's Key Encryption Key, stored in AWS KMS (ap-south-1, customer-managed CMK). PRANA cannot access KEKs.</li>
          <li><strong>PAN tokenisation:</strong> PAN → HMAC-SHA256 (pan_token) for deduplication. PAN → FF3-1 Format-Preserving Encryption (enc_pan) for recovery. Plaintext PAN lifetime: 2ms in memory.</li>
          <li><strong>Zero knowledge by Portal Admin:</strong> PostgreSQL Row-Level Security ensures Portal Admin accounts cannot SELECT on document rows, by database architecture — not policy.</li>
        </ul>
      </Section>

      <Section title="6. Data residency">
        <p>
          All personal data processed under this DPA is stored exclusively in India:
          AWS ap-south-1 (Mumbai, primary) and AWS ap-south-2 (Hyderabad, secondary for disaster recovery).
          No personal data is transferred outside India without explicit consent and lawful basis under DPDP Act 2023.
        </p>
      </Section>

      <Section title="7. Audit rights">
        <p>
          The Data Fiduciary may request an audit of PRANA's data processing activities no more than once
          per calendar year, with 30 days' written notice. PRANA may fulfill audit rights by providing
          a current third-party security audit report (SOC 2 Type II equivalent) in lieu of a direct audit.
        </p>
      </Section>

      <Section title="8. Contact">
        <p>
          For DPA-related queries, contact our Data Protection Officer at{' '}
          <a href="mailto:dpo@prana.in" className="text-indigo-600 hover:underline">dpo@prana.in</a>.
          For legal notices, write to: PRANA Technologies Pvt Ltd, Legal Department, Mumbai, India.
        </p>
      </Section>
    </LegalLayout>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="text-lg font-bold text-slate-900 mb-3 pb-2 border-b border-slate-100">{title}</h2>
      <div className="space-y-3 text-sm text-slate-600 leading-relaxed">{children}</div>
    </section>
  )
}

function Def({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-2 border-b border-slate-100 last:border-0">
      <span className="font-semibold text-slate-800 w-44 flex-shrink-0">{term}</span>
      <span>{children}</span>
    </div>
  )
}
