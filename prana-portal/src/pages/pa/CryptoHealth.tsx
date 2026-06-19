import { useQuery } from '@tanstack/react-query'
import { Lock, CheckCircle, RefreshCw } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function CryptoHealth() {
  const { data, refetch, isFetching } = useQuery({
    queryKey: ['pa-crypto'],
    queryFn: () => api.get('/admin/crypto').then(r => r.data),
    refetchInterval: 300_000,
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Cryptographic Health</h1>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700"
        >
          <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {/* Platform key summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {[
          { label: 'Platform HMAC key', algo: 'HMAC-SHA256', status: data?.hmac_key_status ?? 'UNKNOWN', note: 'Cross-tenant pan_token derivation' },
          { label: 'FF3-1 (FPE) key',  algo: 'FF3-1 AES-256', status: data?.fpe_key_status ?? 'UNKNOWN', note: 'enc_pan format-preserving encryption' },
          { label: 'TOTP AES key',      algo: 'AES-256-GCM',  status: data?.totp_key_status ?? 'UNKNOWN', note: 'totp_secret_enc encryption' },
        ].map(k => (
          <div key={k.label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <div className="flex items-center gap-2 mb-3">
              <Lock size={16} className="text-indigo-500" />
              <span className="font-medium text-slate-800 text-sm">{k.label}</span>
            </div>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-400">Algorithm</span>
                <span className="font-mono text-xs text-slate-600">{k.algo}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Status</span>
                <StatusChip status={k.status} />
              </div>
              <p className="text-xs text-slate-400 mt-2">{k.note}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Tenant KEK table */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-medium text-slate-800">Tenant KEK status</h2>
          <p className="text-xs text-slate-400 mt-0.5">AWS KMS customer-managed keys · ap-south-1</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-slate-400 uppercase tracking-wide">
                <th className="px-5 py-3 text-left font-medium">Tenant</th>
                <th className="px-5 py-3 text-left font-medium">KMS Key ID</th>
                <th className="px-5 py-3 text-center font-medium">State</th>
                <th className="px-5 py-3 text-right font-medium">DEKs</th>
                <th className="px-5 py-3 text-right font-medium">Last rotation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {(data?.tenant_keys ?? []).map((t: any) => (
                <tr key={t.tenant_id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3 font-medium text-slate-700">{t.tenant_name}</td>
                  <td className="px-5 py-3 font-mono text-xs text-slate-500">{t.kms_key_id}</td>
                  <td className="px-5 py-3 text-center"><StatusChip status={t.key_state} /></td>
                  <td className="px-5 py-3 text-right font-mono text-slate-700">{t.dek_count ?? '—'}</td>
                  <td className="px-5 py-3 text-right text-xs text-slate-400 font-mono">
                    {t.last_rotated_at ? fmtDateTime(t.last_rotated_at) : 'Never'}
                  </td>
                </tr>
              ))}
              {!data?.tenant_keys?.length && (
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-sm text-slate-400">No tenant keys found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Algorithm inventory */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">Algorithm inventory</h2>
        <div className="space-y-2">
          {[
            { use: 'PAN dedup token',         algo: 'HMAC-SHA256',    standard: 'NIST FIPS 198-1' },
            { use: 'enc_pan (reversible)',     algo: 'FF3-1 AES-256',  standard: 'NIST SP 800-38G Rev.1' },
            { use: 'DEK storage',             algo: 'AWS KMS AES-256', standard: 'FIPS 140-2 Level 3' },
            { use: 'TOTP secrets',            algo: 'AES-256-GCM',    standard: 'NIST SP 800-38D' },
            { use: 'Passwords',               algo: 'Argon2id',        standard: 'PHC winner (time=2, mem=65536, p=2)' },
            { use: 'JWT signing',             algo: 'RS256',           standard: 'RFC 7518' },
            { use: 'TLS (transit)',           algo: 'TLS 1.3',         standard: 'RFC 8446' },
          ].map(row => (
            <div key={row.use} className="flex items-center gap-4 py-2 border-b border-slate-50 last:border-0">
              <CheckCircle size={13} className="text-emerald-500 shrink-0" />
              <span className="w-48 text-sm text-slate-700 shrink-0">{row.use}</span>
              <span className="font-mono text-xs text-indigo-700 w-40">{row.algo}</span>
              <span className="text-xs text-slate-400">{row.standard}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function StatusChip({ status }: { status: string }) {
  const ok      = ['ENABLED', 'HEALTHY', 'ACTIVE'].includes(status)
  const unknown = status === 'UNKNOWN'
  const cls = ok ? 'bg-emerald-50 text-emerald-700'
            : unknown ? 'bg-slate-100 text-slate-500'
            : 'bg-red-50 text-red-700'
  return (
    <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full ${cls}`}>
      {status}
    </span>
  )
}
