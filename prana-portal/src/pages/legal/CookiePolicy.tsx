import { LegalLayout } from '@/components/LegalLayout'

export function CookiePolicy() {
  return (
    <LegalLayout
      title="Cookie Policy"
      subtitle="PRANA uses only the cookies required to keep you securely logged in. Nothing else."
      badge="Legal · Cookies"
    >
      <p className="text-xs text-slate-400 mb-8">Last updated: June 2025</p>

      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 mb-8 text-xs text-emerald-800 leading-relaxed">
        <strong>Short version:</strong> PRANA uses 2 cookies — one to keep you logged in, one to prevent
        form attacks. No advertising cookies. No analytics cookies. No third-party tracking. Ever.
      </div>

      <Section title="1. What is a cookie?">
        <p>
          A cookie is a small text file stored in your browser by a website. Cookies allow a site to
          remember information about your visit — such as whether you are logged in — across page loads.
        </p>
      </Section>

      <Section title="2. Cookies PRANA uses">
        <table className="w-full text-xs border-collapse mb-4">
          <thead>
            <tr className="bg-slate-100">
              <th className="text-left p-2 border border-slate-200 font-semibold">Cookie name</th>
              <th className="text-left p-2 border border-slate-200 font-semibold">Purpose</th>
              <th className="text-left p-2 border border-slate-200 font-semibold">Duration</th>
              <th className="text-left p-2 border border-slate-200 font-semibold">Type</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['prana_refresh', 'Stores your encrypted refresh token to keep you logged in across sessions', '7 days (rolling)', 'Essential'],
              ['prana_csrf', 'CSRF protection token to prevent cross-site request forgery on form submissions', 'Session', 'Essential'],
            ].map(([name, purpose, dur, type]) => (
              <tr key={name} className="border-b border-slate-100">
                <td className="p-2 border border-slate-200 font-mono text-[10px]">{name}</td>
                <td className="p-2 border border-slate-200 text-slate-600">{purpose}</td>
                <td className="p-2 border border-slate-200 text-slate-500">{dur}</td>
                <td className="p-2 border border-slate-200">
                  <span className="bg-emerald-100 text-emerald-700 text-[10px] font-semibold rounded-full px-2 py-0.5">{type}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          Both cookies are set with <code>HttpOnly</code>, <code>Secure</code>, and <code>SameSite=Strict</code> flags,
          meaning they cannot be read by JavaScript, are only sent over HTTPS, and are never sent in cross-origin requests.
        </p>
      </Section>

      <Section title="3. What we do NOT use">
        <p>PRANA does not use:</p>
        <ul>
          <li>Google Analytics, Mixpanel, Amplitude, or any product analytics platform</li>
          <li>Facebook Pixel, Google Ads tags, or any advertising/remarketing cookies</li>
          <li>Hotjar, FullStory, or any session recording tools</li>
          <li>Third-party chat widgets that set their own cookies</li>
          <li>A/B testing tools that track users across sessions</li>
        </ul>
        <p>
          This is a deliberate architectural choice. PRANA handles sensitive employment documents, and we
          believe no advertising or behavioural tracking infrastructure should ever be embedded in that context.
        </p>
      </Section>

      <Section title="4. Local storage">
        <p>
          PRANA's employer portal uses browser <code>sessionStorage</code> (not cookies) to hold ephemeral
          UI state such as the current tab selection or search query. This data is cleared automatically
          when you close the browser tab and is never synced to our servers.
        </p>
        <p>
          PRANA does <strong>not</strong> store JWT access tokens or any authentication credentials in
          <code>localStorage</code>. Access tokens are held in memory only and discarded on page close.
        </p>
      </Section>

      <Section title="5. Managing cookies">
        <p>
          Because PRANA only uses essential cookies, the platform cannot function if these cookies are
          blocked. If you disable cookies in your browser, you will be unable to log in to the PRANA
          portal or mobile app.
        </p>
        <p>
          You can delete PRANA cookies at any time through your browser settings. Doing so will log you
          out of all active sessions. Your vault data is not affected by cookie deletion.
        </p>
      </Section>

      <Section title="6. Changes to this policy">
        <p>
          If we ever introduce a new cookie (for example, as part of a legitimate security enhancement),
          we will update this page, notify affected users, and obtain consent where required under applicable law.
        </p>
      </Section>

      <Section title="7. Contact">
        <p>
          Questions about our use of cookies? Write to{' '}
          <a href="mailto:privacy@prana.in" className="text-indigo-600 hover:underline">privacy@prana.in</a>.
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
