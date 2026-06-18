import { LegalLayout } from '@/components/LegalLayout'

export function ApiTerms() {
  return (
    <LegalLayout
      title="API Terms of Use"
      subtitle="Rules governing programmatic access to PRANA via the HRMS Integration API."
      badge="Legal · API"
    >
      <p className="text-xs text-slate-400 mb-8">
        Last updated: June 2025 · Applies to: PRANA HRMS API v1 · These terms supplement the PRANA Terms of Use.
      </p>

      <div className="bg-slate-900 rounded-xl p-4 mb-8 text-xs text-slate-300 font-mono leading-relaxed">
        <p className="text-slate-500 mb-2"># Authentication example</p>
        <p>POST https://api.prana.in/ingest/push</p>
        <p>X-PRANA-Key-ID: &lt;your-key-id&gt;</p>
        <p>X-PRANA-Signature: HMAC-SHA256(&lt;request-body&gt;, &lt;signing-secret&gt;)</p>
        <p>Content-Type: application/json</p>
      </div>

      <Section title="1. Who may use the API">
        <p>
          The PRANA HRMS API is available exclusively to organisations that have been onboarded on the
          PRANA platform via the Portal Admin workflow. API access requires:
        </p>
        <ul>
          <li>A completed tenant onboarding with domain verification</li>
          <li>An active OA-Admin account</li>
          <li>An API key generated from the PRANA Portal (Settings → API Keys)</li>
        </ul>
        <p>API keys may not be shared between organisations. Each integration system should have its own key.</p>
      </Section>

      <Section title="2. Authentication">
        <p>Every API request must be authenticated using:</p>
        <ul>
          <li><strong>X-PRANA-Key-ID header:</strong> Your API key identifier (not the secret itself)</li>
          <li><strong>X-PRANA-Signature header:</strong> HMAC-SHA256 of the request body, signed with your signing secret</li>
        </ul>
        <p>
          The signing secret is shown once on creation and never again. Store it in your secrets manager
          (AWS Secrets Manager, HashiCorp Vault, or equivalent). Do not hardcode it in application code
          or commit it to version control.
        </p>
        <p>
          PRANA validates the signature on every request. Requests with missing or invalid signatures
          are rejected with HTTP 401. The key's <code>tenant_id</code> is derived server-side — never
          send <code>tenant_id</code> in the request body.
        </p>
      </Section>

      <Section title="3. Rate limits">
        <table className="w-full text-xs border-collapse mb-4">
          <thead>
            <tr className="bg-slate-100">
              <th className="text-left p-2 border border-slate-200 font-semibold">Endpoint group</th>
              <th className="text-left p-2 border border-slate-200 font-semibold">Rate limit</th>
              <th className="text-left p-2 border border-slate-200 font-semibold">Burst</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Document push (POST /ingest/push)', '500 rpm per key', '50 concurrent'],
              ['Batch push (POST /ingest/batch)', '20 rpm per key', '5 concurrent'],
              ['Status polling (GET /ingest/status/:id)', '1000 rpm per key', 'Unlimited'],
              ['Employee master sync (POST /employees/sync)', '100 rpm per key', '10 concurrent'],
            ].map(([ep, rate, burst]) => (
              <tr key={ep} className="border-b border-slate-100">
                <td className="p-2 border border-slate-200 font-mono text-[10px]">{ep}</td>
                <td className="p-2 border border-slate-200 text-indigo-600 font-semibold">{rate}</td>
                <td className="p-2 border border-slate-200 text-slate-500">{burst}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          Exceeding rate limits returns HTTP 429 with a <code>Retry-After</code> header. Sustained
          violation may result in temporary key suspension. Contact{' '}
          <a href="mailto:integrations@prana.in" className="text-indigo-600 hover:underline">integrations@prana.in</a>{' '}
          to request higher limits for bulk migrations.
        </p>
      </Section>

      <Section title="4. Permitted operations">
        <p>The API is permitted for:</p>
        <ul>
          <li>Pushing employment documents (salary slips, Form 16, offer letters, appointment letters, relieving letters) to employee vaults</li>
          <li>Querying pipeline status of submitted documents</li>
          <li>Syncing your employee master list (name, designation, department — no salary figures)</li>
          <li>Retrieving your organisation's vault health metrics and compliance dashboard data</li>
        </ul>
        <p>The API must NOT be used for:</p>
        <ul>
          <li>Attempting to read or download documents from employee vaults you do not own</li>
          <li>Pushing documents for employees of other organisations</li>
          <li>Querying aggregate analytics data in a manner that could identify individuals (minimum cohort: 30)</li>
          <li>Automated account creation or impersonation of employee sessions</li>
          <li>Load testing or security scanning without prior written approval</li>
        </ul>
      </Section>

      <Section title="5. Document requirements">
        <p>Documents submitted via the API must:</p>
        <ul>
          <li>Be in PDF format (max 10MB per document, max 500 documents per batch)</li>
          <li>Belong to an employee identified by a valid employee ID in your employee master</li>
          <li>Not be password-protected (password-protected documents use a separate in-portal flow)</li>
          <li>Not contain malware, macros, or executable code — the AI pipeline scans for contamination</li>
          <li>Be authentic documents — submitting fabricated documents violates these terms and Indian law</li>
        </ul>
      </Section>

      <Section title="6. Pipeline status and errors">
        <p>
          Every document push returns a <code>pipeline_id</code>. Poll <code>GET /ingest/status/:pipeline_id</code> to track
          progress through the 6 pipeline stages:
        </p>
        <div className="flex flex-wrap gap-2 my-3">
          {['QUEUED', 'ENCRYPTING', 'SCANNING', 'EXTRACTING', 'RESOLVING', 'ROUTED'].map(s => (
            <span key={s} className="text-[10px] font-mono font-bold bg-slate-100 text-slate-700 rounded-full px-2.5 py-1">{s}</span>
          ))}
        </div>
        <p>
          Documents that reach <code>RESOLVING</code> and cannot be matched to an employee appear in the
          Exception Queue and require manual resolution by an OA-Admin in the portal.
        </p>
      </Section>

      <Section title="7. Key management and rotation">
        <ul>
          <li>API keys do not expire by default but should be rotated every 90 days as a security best practice</li>
          <li>Rotate immediately if you suspect the signing secret has been compromised</li>
          <li>Revoked keys take effect immediately — in-flight requests with the revoked key will fail</li>
          <li>Key rotation is zero-downtime: create a new key, update your integration, then revoke the old key</li>
        </ul>
      </Section>

      <Section title="8. Support and integration assistance">
        <p>
          PRANA provides an OpenAPI specification (available in the Portal → Settings → API Keys → Download Spec)
          and a Postman collection for integration testing. For integration support, write to{' '}
          <a href="mailto:integrations@prana.in" className="text-indigo-600 hover:underline">integrations@prana.in</a>.
          For security incidents involving API keys, write to{' '}
          <a href="mailto:security@prana.in" className="text-indigo-600 hover:underline">security@prana.in</a>.
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
