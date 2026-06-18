import { useQuery } from '@tanstack/react-query'
import { BarChart3, Info } from 'lucide-react'
import { api } from '@/lib/api'

export function RateLimits() {
  const { data, isLoading } = useQuery({
    queryKey: ['pa-rate-limits'],
    queryFn: () => api.get('/admin/rate-limits').then(r => r.data),
    refetchInterval: 30_000,
  })

  const keys: any[] = data?.keys ?? []
  const tenantDefaults: any[] = data?.tenant_defaults ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Rate Limits</h1>
        <p className="text-xs text-slate-400 mt-1">
          Per-API-key request quotas are enforced by Kong API Gateway via Redis token buckets.
          Tenant defaults apply when no per-key override is set.
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Active API keys',        value: data?.total_keys ?? '—' },
          { label: 'Throttled (last 1h)',     value: data?.throttled_1h ?? '—' },
          { label: 'Avg req/min (keyed)',     value: data?.avg_rpm ?? '—' },
          { label: 'Platform default rpm',    value: data?.platform_default_rpm ?? '—' },
        ].map(c => (
          <div key={c.label} className="stat-card">
            <p className="text-2xl font-bold font-mono text-slate-800">{c.value}</p>
            <p className="text-xs text-slate-500 mt-1">{c.label}</p>
          </div>
        ))}
      </div>

      {/* Tenant default rate limits — always visible */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
          <Info size={14} className="text-sky-500" />
          <h2 className="font-medium text-slate-800">Per-tenant default rate limits</h2>
          <span className="ml-auto text-xs text-slate-400">
            Enforced by Kong · Redis token bucket · burst = 2× limit
          </span>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-xs text-slate-400 uppercase tracking-wide">
              <th className="px-5 py-3 text-left font-medium">Tenant</th>
              <th className="px-5 py-3 text-right font-medium">Default rpm</th>
              <th className="px-5 py-3 text-right font-medium">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading && (
              <tr><td colSpan={3} className="px-5 py-8 text-center text-slate-400">Loading…</td></tr>
            )}
            {!isLoading && tenantDefaults.map((t: any) => (
              <tr key={t.tenant_id} className="hover:bg-slate-50/50">
                <td className="px-5 py-3 font-medium text-slate-700">{t.tenant_name}</td>
                <td className="px-5 py-3 text-right font-mono text-slate-700">{t.default_rpm}</td>
                <td className="px-5 py-3 text-right">
                  <span className={`badge ${t.source === 'tenant_config' ? 'badge-emerald' : 'badge-muted'}`}>
                    {t.source === 'tenant_config' ? 'custom' : 'platform default'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Per-key overrides */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
          <BarChart3 size={14} className="text-violet-500" />
          <h2 className="font-medium text-slate-800">API key rate limits (HRMS integrations)</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-slate-400 uppercase tracking-wide">
                <th className="px-5 py-3 text-left font-medium">Tenant</th>
                <th className="px-5 py-3 text-left font-medium">Label</th>
                <th className="px-5 py-3 text-right font-medium">Key rpm</th>
                <th className="px-5 py-3 text-right font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {isLoading && (
                <tr><td colSpan={4} className="px-5 py-8 text-center text-slate-400">Loading…</td></tr>
              )}
              {!isLoading && keys.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-5 py-8 text-center text-slate-400">
                    No HRMS API keys issued yet. Use "API Keys" to issue one.
                  </td>
                </tr>
              )}
              {keys.map((k: any) => (
                <tr key={k.api_key_id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3 text-slate-600">{k.tenant_name}</td>
                  <td className="px-5 py-3 text-slate-700 font-medium">{k.label ?? '—'}</td>
                  <td className="px-5 py-3 text-right font-mono text-slate-700">{k.rate_limit_rpm}</td>
                  <td className="px-5 py-3 text-right">
                    <span className={`badge ${k.status === 'ACTIVE' ? 'badge-emerald' : 'badge-muted'}`}>
                      {k.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
