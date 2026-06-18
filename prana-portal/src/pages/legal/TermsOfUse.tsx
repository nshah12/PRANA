import { LegalLayout } from '@/components/LegalLayout'

export function TermsOfUse() {
  return (
    <LegalLayout
      title="Terms of Use"
      subtitle="The rules that govern your use of the PRANA platform — for employees, organisations, and integrators."
      badge="Legal · Terms"
    >
      <p className="text-xs text-slate-400 mb-8">Last updated: June 2025 · Governing law: India · Jurisdiction: Courts of Mumbai</p>

      <Section title="1. Acceptance">
        <p>
          By accessing or using PRANA — whether as an individual employee, an organisation administrator, or
          an API integrator — you agree to these Terms of Use. If you are accessing PRANA on behalf of an
          organisation, you represent that you have authority to bind that organisation.
        </p>
        <p>
          These terms apply to: the PRANA mobile app, the PRANA employer portal at <code>portal.prana.in</code>,
          and the PRANA HRMS API.
        </p>
      </Section>

      <Section title="2. The PRANA service">
        <p>PRANA provides:</p>
        <ul>
          <li><strong>For employees:</strong> A permanent, portable career document vault that stores employment documents pushed by your employers, allows secure sharing via C-Share links, and provides AI-derived career insights.</li>
          <li><strong>For organisations:</strong> A portal and API to push HR documents (salary slips, Form 16, offer letters) to employee vaults with AI governance, and management tools for OA-Operators, OA-Admins, CHRO, CFO, and Infosec roles.</li>
          <li><strong>For integrators:</strong> An HRMS API (OpenAPI-compatible) for automated document push at scale.</li>
        </ul>
      </Section>

      <Section title="3. Accounts and authentication">
        <ul>
          <li>All portal accounts require TOTP two-factor authentication. You are responsible for securing your authenticator device.</li>
          <li>Organisation accounts are locked after 3 failed TOTP attempts for Portal Admin roles, and 5 attempts for other roles.</li>
          <li>You must not share credentials, share sessions, or circumvent authentication controls.</li>
          <li>PRANA accounts use your employer's corporate email domain. Personal email addresses are not permitted for organisation accounts.</li>
        </ul>
      </Section>

      <Section title="4. Permitted use">
        <p>You may use PRANA only for its intended purpose: managing legitimate employment documents for Indian workforce compliance. Specifically, you must not:</p>
        <ul>
          <li>Upload fabricated, forged, or altered employment documents</li>
          <li>Use PRANA to process documents for individuals who have not consented</li>
          <li>Attempt to access another employee's vault or decrypt documents not addressed to you</li>
          <li>Exceed the API rate limit of 500 requests per minute without written approval</li>
          <li>Reverse-engineer, scrape, or attempt to extract raw salary figures from the platform</li>
          <li>Use PRANA's aggregate analytics to derive individual-level salary data</li>
        </ul>
      </Section>

      <Section title="5. Organisation responsibilities">
        <p>Organisations onboarded on PRANA agree to:</p>
        <ul>
          <li>Push only documents belonging to employees employed or previously employed by that organisation</li>
          <li>Maintain at least one active OA-Admin account at all times</li>
          <li>Obtain and maintain valid DPDP consent from employees before document push</li>
          <li>Report suspected misuse, credential compromise, or data incidents within 24 hours of discovery to <a href="mailto:security@prana.in" className="text-indigo-600 hover:underline">security@prana.in</a></li>
          <li>Keep API keys confidential and rotate them immediately if compromised</li>
        </ul>
      </Section>

      <Section title="6. Intellectual property">
        <p>
          PRANA owns all rights to the platform, including the 6-stage AI pipeline, the NIK identity
          resolution model, the C-Share cryptographic protocol, and all platform software. You do not
          acquire any rights to PRANA's IP by using the service.
        </p>
        <p>
          Your documents remain yours. PRANA holds your documents as a data processor, not as the owner.
          We do not claim any rights over the content of your employment documents.
        </p>
      </Section>

      <Section title="7. Liability and warranties">
        <p>
          PRANA provides the platform "as is" and "as available". We do not guarantee 100% uptime but
          target 99.9% availability for the API and vault access services.
        </p>
        <p>
          PRANA is not liable for: (a) actions taken by employers on the platform within their permitted
          scope; (b) delays caused by AWS infrastructure or third-party OCR services; (c) losses arising
          from use of share links you generate.
        </p>
        <p>
          Our total liability to you in any 12-month period is limited to the fees you paid to PRANA in
          that period, or ₹10,000, whichever is higher.
        </p>
      </Section>

      <Section title="8. Termination">
        <p>
          You may close your account at any time from the mobile app. Organisations may offboard via the
          Portal Admin. On termination, your documents are deleted per the retention schedule in our{' '}
          <a href="/legal/privacy" className="text-indigo-600 hover:underline">Privacy Policy</a>. Audit logs are
          retained for the statutory 7-year period even after account closure.
        </p>
      </Section>

      <Section title="9. Governing law">
        <p>
          These terms are governed by the laws of India. Disputes shall be subject to the exclusive
          jurisdiction of the courts in Mumbai, Maharashtra. PRANA is registered and operates under
          Indian company law.
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
