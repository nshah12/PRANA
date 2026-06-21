/**
 * CisoDigest — date-range queryable InfoSec digest.
 * CISO sees full IP in incident details (per document-sharing.md rules).
 * No PAN, salary, or document content — only access metadata.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ShieldCheck, ShieldAlert, Activity, Download, Settings } from 'lucide-react'
import { api } from '@/lib/api'
import { Link } from 'react-router-dom'
import { DigestDatePicker, type DateWindow } from '@/components/digest/DigestDatePicker'

function todayISO() { return new Date().toISOString().split('T')[0] }
function daysAgoISO(n: number) {
  const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().split('T')[0]
}

const SEV_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  HIGH:   { bg: 'bg-red-50',    text: 'text-red-700',    label: 'High'   },
  MEDIUM: { bg: 'bg-amber-50',  text: 'text-amber-700',  label: 'Medium' },
  LOW:    { bg: 'bg-emerald-50',text: 'text-emerald-700',label: 'Low'    },
}

const CHANNEL_COLOR: Record<string, string> = {
  MOBILE:     '#059669',
  PORTAL:     '#0891b2',
  SHARE_LINK: '#f59e0b',
  API:        '#6366f1',
  WEB:        '#94a3b8',
}

export function CisoDigest() {
  const [window, setWindow] = useState<DateWindow>({ from: daysAgoISO(7), to: todayISO() })

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['ciso-digest', window.from, window.to],
    queryFn:  () => api.get(`/v1/ciso/digest/weekly?from=${window.from}&to=${window.to}`)
                       .then(r => r.data.digest),
    enabled: !!window.from && !!window.to,
  })

  const header = (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">InfoSec Digest</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {data ? `${data.from} → ${data.to}` : 'Loading…'} · access metadata only · no PAN
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/org/digest-settings"
                className="flex items-center gap-1.5 text-sm text-slate-500 border border-slate-200
                           px-3 py-1.5 rounded-lg hover:bg-canvas2">
            <Settings size={13}/> Settings
          </Link>
          <button className="flex items-center gap-1.5 text-sm text-slate-500 border border-slate-200
                             px-3 py-1.5 rounded-lg hover:bg-canvas2">
            <Download size={13}/> Export
          </button>
        </div>
      </div>
      <DigestDatePicker
        accentColor="bg-emerald-600"
        accentText="text-emerald-600"
        accentBorder="border-emerald-600"
        onChange={setWindow}
      />
    </div>
  )

  if (isLoading) return (
    <div className="space-y-6 max-w-2xl">
      {header}
      <div className="animate-pulse space-y-4">
        <div className="grid grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-slate-100 rounded-xl" />)}
        </div>
        <div className="h-40 bg-slate-100 rounded-xl" />
      </div>
    </div>
  )

  if (isError) return (
    <div className="space-y-6 max-w-2xl">
      {header}
      <div className="flex flex-col items-center justify-center py-20 text-slate-400">
        <p className="text-sm">Failed to load CISO digest.</p>
        <button onClick={() => refetch()} className="mt-3 text-xs text-emerald-600 hover:underline">Retry</button>
      </div>
    </div>
  )

  const totalAccesses  = data?.total_accesses ?? 0
  const anomaliesTotal = data?.anomalies_total ?? 0
  const anomaliesOpen  = data?.anomalies_open ?? 0
  const forceLogouts   = data?.force_logouts ?? 0
  const shareTokens    = data?.share_tokens_period ?? 0
  const channels       = data?.by_channel ?? []
  const incidents      = data?.incidents ?? []
  const maxChannelCount = Math.max(...channels.map((c: any) => c.count), 1)

  return (
    <div className="space-y-6 max-w-2xl">
      {header}

      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Doc accesses',  value: totalAccesses,  icon: <Activity size={13}/>,    color: 'text-emerald-600', note: 'All watermarked & logged' },
          { label: 'Anomalies',     value: anomaliesTotal, icon: <ShieldAlert size={13}/>, color: anomaliesTotal > 0 ? 'text-amber-500' : 'text-slate-400', note: `${anomaliesOpen} open` },
          { label: 'Force-logouts', value: forceLogouts,   icon: <ShieldAlert size={13}/>, color: forceLogouts > 0 ? 'text-red-500' : 'text-slate-400', note: 'bulk access events' },
          { label: 'Share tokens',  value: shareTokens,    icon: <Activity size={13}/>,    color: 'text-slate-500', note: 'issued this period' },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-4">
            <p className="text-xs text-slate-400">{s.label}</p>
            <p className="text-xl font-bold font-mono text-slate-800 mt-1">{s.value}</p>
            <div className={`flex items-center gap-1 mt-1 text-xs font-medium ${s.color}`}>
              {s.icon} {s.note}
            </div>
          </div>
        ))}
      </div>

      {channels.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
          <h2 className="text-sm font-medium text-slate-700 mb-4">Access by channel</h2>
          <div className="space-y-2.5">
            {channels.map((ch: any) => {
              const pct = Math.round((ch.count / maxChannelCount) * 100)
              const color = CHANNEL_COLOR[ch.channel] ?? CHANNEL_COLOR.WEB
              return (
                <div key={ch.channel} className="flex items-center gap-3">
                  <span className="text-xs text-slate-500 w-24 text-right flex-shrink-0">
                    {ch.channel.replace(/_/g, ' ')}
                  </span>
                  <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
                  </div>
                  <span className="text-xs font-mono text-slate-700 w-12 text-right">{ch.count.toLocaleString()}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {incidents.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100">
            <h2 className="text-sm font-medium text-slate-700">Incidents & security events</h2>
          </div>
          <div className="divide-y divide-slate-50">
            {incidents.map((inc: any) => {
              const sev = SEV_STYLE[inc.severity?.toUpperCase()] ?? SEV_STYLE.LOW
              return (
                <div key={inc.anomaly_id} className="flex items-start gap-3 px-5 py-3">
                  <span className={`flex-shrink-0 mt-0.5 text-xs font-medium px-2 py-0.5 rounded-full ${sev.bg} ${sev.text}`}>
                    {sev.label}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800">{inc.rule_name?.replace(/_/g, ' ')}</p>
                    {inc.detected_at && (
                      <p className="text-xs text-slate-400 mt-0.5">
                        {new Date(inc.detected_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
                      </p>
                    )}
                  </div>
                  <span className={`flex-shrink-0 mt-0.5 text-xs font-medium px-2 py-0.5 rounded-full
                    ${inc.resolved ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                    {inc.resolved ? 'Resolved' : 'Open'}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {incidents.length === 0 && anomaliesTotal === 0 && (
        <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
          <ShieldCheck size={16} className="text-emerald-600 flex-shrink-0"/>
          <p className="text-sm text-emerald-800">
            No anomalies or incidents in this period. Security posture is clean.
          </p>
        </div>
      )}

      {anomaliesOpen > 0 && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
          <ShieldAlert size={15} className="text-amber-500 flex-shrink-0"/>
          <p className="text-sm text-amber-800 flex-1">
            {anomaliesOpen} open anomal{anomaliesOpen === 1 ? 'y' : 'ies'} — review in security dashboard.
          </p>
          <Link to="/org/anomaly-queue"
                className="text-sm font-medium text-amber-700 border border-amber-300
                           px-3 py-1.5 rounded-lg hover:bg-amber-100 flex-shrink-0">
            Review →
          </Link>
        </div>
      )}
    </div>
  )
}
