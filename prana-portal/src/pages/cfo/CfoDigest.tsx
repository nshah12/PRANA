/**
 * CfoDigest — date-range queryable CFO digest.
 * Cost figures are CFO-configured estimates (never extracted salary data).
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, AlertTriangle, Download, Settings } from 'lucide-react'
import { api } from '@/lib/api'
import { Link } from 'react-router-dom'
import { DigestDatePicker, type DateWindow } from '@/components/digest/DigestDatePicker'

function todayISO() { return new Date().toISOString().split('T')[0] }
function daysAgoISO(n: number) {
  const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().split('T')[0]
}

function formatRupee(val: number | null): string {
  if (val == null) return '—'
  if (val >= 1_00_00_000) return `₹${(val / 1_00_00_000).toFixed(1)} Cr`
  if (val >= 1_00_000)    return `₹${(val / 1_00_000).toFixed(1)}L`
  return `₹${val.toLocaleString('en-IN')}`
}

export function CfoDigest() {
  const [window, setWindow] = useState<DateWindow>({ from: daysAgoISO(7), to: todayISO() })

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['cfo-digest', window.from, window.to],
    queryFn:  () => api.get(`/v1/cfo/digest/weekly?from=${window.from}&to=${window.to}`)
                       .then(r => r.data.digest),
    enabled: !!window.from && !!window.to,
  })

  const header = (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">CFO Digest</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {data ? `${data.from} → ${data.to}` : 'Loading…'} · cost figures are CFO-configured estimates
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
        accentColor="bg-cyan-600"
        accentText="text-cyan-600"
        accentBorder="border-cyan-600"
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
        <p className="text-sm">Failed to load CFO digest.</p>
        <button onClick={() => refetch()} className="mt-3 text-xs text-cyan-600 hover:underline">Retry</button>
      </div>
    </div>
  )

  const budget     = data?.headcount_budget
  const headcount  = data?.headcount ?? 0
  const budgetPct  = budget ? Math.round((headcount / budget) * 100) : null
  const avgCTC     = data?.cost_indicators?.avg_ctc_estimate
  const replCost   = data?.cost_indicators?.replacement_cost_estimate
  const exits      = data?.exits ?? 0

  const compliance = data?.compliance_by_doc_type ?? {}
  const compRows = Object.entries(compliance).map(([doc, covered]) => ({
    doc, covered: covered as number,
    pct: Math.round(((covered as number) / Math.max(headcount, 1)) * 100),
  }))

  return (
    <div className="space-y-6 max-w-2xl">
      {header}

      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Headcount',          value: headcount,              sub: budget ? `Budget: ${budget}` : null, up: true  },
          { label: 'Exits',              value: exits,                  sub: 'this period', up: false },
          { label: 'Joiners',            value: data?.joiners ?? 0,     sub: 'this period', up: true  },
          { label: 'Anomalies pending',  value: data?.anomalies_pending ?? 0, sub: 'awaiting ack', up: false },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-4">
            <p className="text-xs text-slate-400">{s.label}</p>
            <p className="text-xl font-bold font-mono text-slate-800 mt-1">{s.value}</p>
            {s.sub && (
              <div className={`flex items-center gap-1 mt-1 text-xs font-medium
                ${s.up ? 'text-emerald-600' : (s.value > 0 ? 'text-amber-500' : 'text-slate-400')}`}>
                {s.up ? <TrendingUp size={10}/> : (s.value > 0 ? <TrendingDown size={10}/> : null)}
                {s.sub}
              </div>
            )}
          </div>
        ))}
      </div>

      {(avgCTC || replCost) && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium text-slate-700">Cost indicators</h2>
            <span className="text-xs text-slate-400 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded-full">
              {data?.cost_indicators?.note}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {avgCTC && (
              <div className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Est. monthly payroll</p>
                <p className="text-base font-bold font-mono text-slate-800 mt-1">
                  {formatRupee(avgCTC * headcount)}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">{headcount} × avg CTC</p>
              </div>
            )}
            {replCost && exits > 0 && (
              <div className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Attrition cost est.</p>
                <p className="text-base font-bold font-mono text-slate-800 mt-1">
                  {formatRupee(replCost * exits)}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">{exits} exits × replacement est.</p>
              </div>
            )}
            {budget && budget > headcount && avgCTC && (
              <div className="bg-slate-50 rounded-lg p-3">
                <p className="text-xs text-slate-400">Unfilled budget</p>
                <p className="text-base font-bold font-mono text-slate-800 mt-1">
                  {formatRupee(avgCTC * (budget - headcount) / 12)}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">{budget - headcount} open roles est.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {budget && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
          <h2 className="text-sm font-medium text-slate-700 mb-4">Headcount vs budget</h2>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500 w-20 text-right flex-shrink-0">Headcount</span>
            <div className="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full"
                   style={{ width: `${Math.min(budgetPct ?? 0, 100)}%`,
                            background: (budgetPct ?? 0) >= 95 ? '#10b981' : '#0891b2' }} />
            </div>
            <span className={`text-sm font-mono font-bold w-10 text-right
              ${(budgetPct ?? 0) >= 95 ? 'text-emerald-600' : 'text-cyan-600'}`}>
              {budgetPct}%
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-2 text-right">
            {headcount} of {budget} budgeted positions filled
          </p>
        </div>
      )}

      {compRows.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
          <h2 className="text-sm font-medium text-slate-700 mb-4">Financial document compliance</h2>
          <div className="space-y-2.5">
            {compRows.map(row => (
              <div key={row.doc} className="flex items-center gap-3">
                <span className="text-xs text-slate-500 w-28 text-right flex-shrink-0">
                  {row.doc.replace(/_/g, ' ')}
                </span>
                <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full"
                       style={{ width: `${row.pct}%`,
                                background: row.pct >= 95 ? '#10b981' : row.pct >= 80 ? '#0891b2' : '#f59e0b' }} />
                </div>
                <span className={`text-xs font-mono w-8 text-right font-medium
                  ${row.pct >= 95 ? 'text-emerald-600' : row.pct >= 80 ? 'text-cyan-600' : 'text-amber-600'}`}>
                  {row.pct}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(data?.anomalies_pending ?? 0) > 0 && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
          <AlertTriangle size={15} className="text-amber-500 flex-shrink-0"/>
          <p className="text-sm text-amber-800 flex-1">
            {data?.anomalies_pending} anomal{data?.anomalies_pending === 1 ? 'y' : 'ies'} pending acknowledgement.
            SLA: 48 hours from detection.
          </p>
          <Link to="/org/anomalies"
                className="text-sm font-medium text-amber-700 border border-amber-300
                           px-3 py-1.5 rounded-lg hover:bg-amber-100 flex-shrink-0">
            Review →
          </Link>
        </div>
      )}
    </div>
  )
}
