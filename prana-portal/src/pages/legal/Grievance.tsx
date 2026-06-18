import { LegalLayout } from '@/components/LegalLayout'

export function Grievance() {
  return (
    <LegalLayout
      title="Grievance Redressal"
      subtitle="How to raise, track, and escalate a privacy or data-related complaint with PRANA."
      badge="Legal · Grievance"
    >
      <p className="text-xs text-slate-400 mb-8">
        Last updated: June 2025 · As required under DPDP Act 2023, Section 13 and IT Act 2000, Rule 5(9)
      </p>

      <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 mb-8 text-xs text-indigo-800 leading-relaxed">
        <strong>Your right to grievance redressal is guaranteed under the DPDP Act 2023.</strong> PRANA is
        required to acknowledge your grievance within 48 hours and resolve it within 30 days. If you are
        unsatisfied with our resolution, you have the right to escalate to the Data Protection Board of India.
      </div>

      <Section title="1. Who can file a grievance?">
        <p>Any person whose personal data PRANA has processed can file a grievance, including:</p>
        <ul>
          <li>Employees (Data Principals) whose documents are stored in a PRANA vault</li>
          <li>Former employees whose documents were pushed by a previous employer</li>
          <li>Organisation administrators who believe PRANA has mishandled their organisation's data</li>
          <li>Any person who believes their data rights under the DPDP Act 2023 have been violated</li>
        </ul>
      </Section>

      <Section title="2. What you can raise a grievance about">
        <ul>
          <li>Unauthorised access to your vault or documents</li>
          <li>Failure to process your erasure, correction, or access request within the statutory period</li>
          <li>Documents appearing in your vault that you did not authorise</li>
          <li>A share link that was not revoked after your revocation request</li>
          <li>Inaccurate data in your Career Timeline or Vault Health Score</li>
          <li>Any suspected breach of confidentiality, encryption failure, or data leak</li>
          <li>Non-compliance with your consent withdrawal</li>
        </ul>
      </Section>

      <Section title="3. How to raise a grievance">
        <p><strong>Step 1 — In-app (preferred):</strong></p>
        <p>
          Open the PRANA mobile app → Profile → DPDP Rights Centre → Raise a Grievance.
          This creates a tracked grievance ticket with a reference number. You will receive an
          acknowledgement within 48 hours.
        </p>

        <p><strong>Step 2 — Email:</strong></p>
        <p>
          Write to our Grievance Officer at{' '}
          <a href="mailto:grievance@prana.in" className="text-indigo-600 hover:underline">grievance@prana.in</a>.
          Include: your registered email address or employee ID, a description of the issue, and any
          relevant dates or evidence. We will acknowledge within 48 hours and provide a reference number.
        </p>

        <p><strong>Step 3 — Written:</strong></p>
        <p>
          Write to: Grievance Officer, PRANA Technologies Pvt Ltd, [Registered Address], Mumbai,
          Maharashtra, India. Written grievances will be acknowledged within 5 business days.
        </p>
      </Section>

      <Section title="4. Resolution timeline">
        <table className="w-full text-xs border-collapse mb-4">
          <thead>
            <tr className="bg-slate-100">
              <th className="text-left p-2 border border-slate-200 font-semibold">Stage</th>
              <th className="text-left p-2 border border-slate-200 font-semibold">Timeline</th>
              <th className="text-left p-2 border border-slate-200 font-semibold">What happens</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Acknowledgement', '48 hours', 'You receive a reference number and initial assessment'],
              ['Investigation', '7 days', 'Grievance Officer reviews logs, encryption records, and share tokens'],
              ['Resolution', '30 days', 'Written resolution with remediation steps or explanation'],
              ['Escalation (if unsatisfied)', '—', 'Data Protection Board of India (once constituted under DPDP Act)'],
            ].map(([stage, time, what]) => (
              <tr key={stage} className="border-b border-slate-100">
                <td className="p-2 border border-slate-200 font-medium">{stage}</td>
                <td className="p-2 border border-slate-200 text-indigo-600 font-semibold">{time}</td>
                <td className="p-2 border border-slate-200 text-slate-600">{what}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="5. Our Grievance Officer">
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
          <p className="font-semibold text-slate-800 mb-1">Grievance Officer — PRANA Technologies Pvt Ltd</p>
          <p>Email: <a href="mailto:grievance@prana.in" className="text-indigo-600 hover:underline">grievance@prana.in</a></p>
          <p>Response hours: Monday–Friday, 9am–6pm IST</p>
          <p className="text-xs text-slate-400 mt-2">
            The Grievance Officer is a senior PRANA employee with authority to initiate investigation,
            access audit logs, and order remediation actions. Their identity is disclosed to users who
            raise a formal grievance.
          </p>
        </div>
      </Section>

      <Section title="6. Escalation to the Data Protection Board">
        <p>
          If you are not satisfied with PRANA's resolution, you have the right to escalate your complaint
          to the Data Protection Board of India (DPBI), once constituted under the DPDP Act 2023. The DPBI
          has the power to award compensation and impose penalties.
        </p>
        <p>
          PRANA will cooperate fully with any DPBI investigation and will not retaliate against any user
          who exercises this right.
        </p>
      </Section>

      <Section title="7. Evidence we may request">
        <p>To investigate your grievance effectively, we may request:</p>
        <ul>
          <li>Your registered email address or PRANA employee ID</li>
          <li>Screenshot or description of the issue</li>
          <li>Approximate date and time of the incident</li>
          <li>The employer organisation name (for vault-related issues)</li>
        </ul>
        <p>
          You are never required to provide your PAN, bank details, or password to raise a grievance.
          If anyone claiming to be PRANA asks for these, report it to{' '}
          <a href="mailto:security@prana.in" className="text-indigo-600 hover:underline">security@prana.in</a> immediately.
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
