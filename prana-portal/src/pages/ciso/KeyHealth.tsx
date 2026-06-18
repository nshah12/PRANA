import { useQuery } from '@tanstack/react-query'
import { Key, CheckCircle, AlertTriangle } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function KeyHealth() {
  const { data } = useQuery({
    queryKey: ['ciso-key-health'],
    queryFn: () => api.get('/v1/ciso/keys').then(r => r.data),
    refetchInterval: 300_000,
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Key Health</h1>
        <span className="text-xs font-mono text-slate-400">AWS KMS · ap-south-1</span>
      </div>

      {/* KEK status */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <div className="flex items-center gap-3 mb-4">
          <Key size={18} className="text-indigo-500" />
          <h2 className="font-medium text-slate-800">Tenant KEK</h2>
          <StatusPill status={data?.kek_status} />
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
          <Kv label="KMS Key ID" value={data?.kek_key_id ?? '—'} mono />
          <Kv label="Key state"  value={data?.kek_state ?? '—'} />
          <Kv label="Created"    value={data?.kek_created_at ? fmtDateTime(data.kek_created_at) : '—'} mono />
          <Kv label="Last used"  value={data?.kek_last_used_at ? fmtDateTime(data.kek_last_used_at) : 'Never'} mono />
          <Kv label="Region"     value="ap-south-1" />
          <Kv label="DEKs encrypted" value={data?.dek_count ?? '—'} mono />
        </div>
      </div>

      {/* TOTP secret status */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <div className="flex items-center gap-3 mb-4">
          <Key size={18} className="text-sky-500" />
          <h2 className="font-medium text-slate-800">TOTP Secret Encryption</h2>
          <StatusPill status={data?.totp_enc_status} />
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <Kv label="Algorithm"   value="AES-256-GCM" />
          <Kv label="Secrets count" value={data?.totp_secret_count ?? '—'} mono />
        </div>
      </div>

      {/* Recent key events */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-medium text-slate-800">Recent KMS events</h2>
        </div>
        <div className="divide-y divide-slate-50">
          {(data?.events ?? []).map((e: any, i: number) => (
            <div key={i} className="px-5 py-3 flex items-center gap-4">
              {e.outcome === 'SUCCESS'
                ? <CheckCircle size={14} className="text-emerald-500 shrink-0" />
                : <AlertTriangle size={14} className="text-red-500 shrink-0" />}
              <span className="flex-1 text-sm text-slate-700">{e.event_type}</span>
              <span className="text-xs text-slate-400 font-mono whitespace-nowrap">{fmtDateTime(e.occurred_at)}</span>
            </div>
          ))}
          {!data?.events?.length && (
            <p className="px-5 py-8 text-sm text-slate-400 text-center">No KMS events recorded.</p>
          )}
        </div>
      </div>
    </div>
  )
}

function Kv({ label, value, mono }: { label: string; value: string | number; mono?: boolean }) {
  return (
    <div>
      <p className="text-xs text-slate-400">{label}</p>
      <p className={`text-slate-700 mt-0.5 ${mono ? 'font-mono text-xs' : ''}`}>{value}</p>
    </div>
  )
}

function StatusPill({ status }: { status?: string }) {
  if (!status) return null
  const ok = status === 'HEALTHY' || status === 'ENABLED'
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
      {status}
    </span>
  )
}
