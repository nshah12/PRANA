import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell, CartesianGrid, Legend,
} from 'recharts'
import { TrendingUp, Lock, Info } from 'lucide-react'
import { api } from '@/lib/api'

interface BandItem {
  grade:          string
  department:     string
  period:         string
  sample_count:   number
  suppressed:     boolean
  p25:            number | null
  p50:            number | null
  p75:            number | null
  computed_at:    string
  data_freshness: string
}

interface OptInStats {
  total_active_employees: number
  opted_in:               number
  not_opted_in:           number
  opt_in_rate_pct:        number
}

// Format paise → lakhs label for chart axis only (never shown as ₹ text in tooltip)
function paiseLakhsLabel(paise: number): string {
  const lakhs = paise / 10_000_000  // 1 lakh = 10M paise
  return `${lakhs.toFixed(1)}L`
}

// Custom tooltip — shows percentile labels, NOT ₹ amounts
function BandTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload as BandItem
  if (!d || d.suppressed) return null
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-4 py-3 text-sm">
      <p className="font-semibold text-slate-800 mb-2">{d.grade} · {d.department}</p>
      <div className="space-y-1">
        <p className="text-slate-500">P75 <span className="text-violet-600 font-medium">{paiseLakhsLabel(d.p75!)}</span></p>
        <p className="text-slate-500">Median <span className="text-sky-600 font-medium">{paiseLakhsLabel(d.p50!)}</span></p>
        <p className="text-slate-500">P25 <span className="text-emerald-600 font-medium">{paiseLakhsLabel(d.p25!)}</span></p>
      </div>
      <p className="text-xs text-slate-400 mt-2">{d.sample_count} contributors</p>
    </div>
  )
}

export function CompBenchmarking() {
  const [filterDept, setFilterDept] = useState('')
  const [filterGrade, setFilterGrade] = useState('')
  const [period, setPeriod]         = useState('')

  const { data, isLoading, error } = useQuery({
    queryKey: ['chro-comp-bands', filterDept, filterGrade, period],
    queryFn: () => api.get('/v1/benchmarking/org/bands', {
      params: {
        ...(filterDept  ? { department: filterDept }  : {}),
        ...(filterGrade ? { grade: filterGrade }       : {}),
        ...(period      ? { period }                   : {}),
      },
    }).then(r => r.data),
  })

  const { data: optInStats } = useQuery<OptInStats>({
    queryKey: ['chro-opt-in-stats'],
    queryFn:  () => api.get('/v1/benchmarking/org/opt-in-stats').then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })

  const bands: BandItem[]  = data?.items ?? []
  const published          = bands.filter(b => !b.suppressed)
  const suppressed         = bands.filter(b => b.suppressed)

  // Build chart data — spread between p25 and p75, median as reference
  const chartData = published.map(b => ({
    ...b,
    name:       `${b.grade}`,
    spread:     (b.p75! - b.p25!) as number,   // bar height = spread
    base:       b.p25!,                          // bar starts at p25
    median_pos: b.p50!,
  }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Comp Benchmarking</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Your org's compensation bands vs. verified market data
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500 bg-sky-50 border border-sky-100 rounded-lg px-3 py-2">
          <Info size={13} className="text-sky-500 shrink-0" />
          Bands require ≥ 50 employee contributions (k-anonymity). Below threshold → suppressed.
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        {[
          { label: 'Department', value: filterDept,  set: setFilterDept,  placeholder: 'All departments' },
          { label: 'Grade',      value: filterGrade, set: setFilterGrade, placeholder: 'All grades'      },
          { label: 'Period',     value: period,       set: setPeriod,      placeholder: 'All periods'     },
        ].map(f => (
          <div key={f.label}>
            <label className="block text-xs text-slate-500 mb-1">{f.label}</label>
            <input
              value={f.value}
              onChange={e => f.set(e.target.value)}
              placeholder={f.placeholder}
              className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500/30 w-40"
            />
          </div>
        ))}
      </div>

      {isLoading && (
        <div className="grid grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse" />
          ))}
        </div>
      )}

      {error && (
        <div className="text-center py-16 text-slate-400">
          <p className="font-medium">Failed to load comp bands</p>
        </div>
      )}

      {!isLoading && !error && (
        <>
          {/* Summary KPIs */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="stat-card stat-card-sky">
              <p className="text-2xl font-bold font-mono text-slate-800">{published.length}</p>
              <p className="text-xs text-slate-500 mt-1">Published bands</p>
            </div>
            <div className="stat-card stat-card-amber">
              <p className="text-2xl font-bold font-mono text-slate-800">{suppressed.length}</p>
              <p className="text-xs text-slate-500 mt-1">Suppressed (growing)</p>
            </div>
            <div className="stat-card stat-card-emerald">
              <p className="text-2xl font-bold font-mono text-slate-800">
                {published.reduce((s, b) => s + b.sample_count, 0).toLocaleString('en-IN')}
              </p>
              <p className="text-xs text-slate-500 mt-1">Total contributors</p>
            </div>
            <div className="stat-card stat-card-violet">
              <p className="text-2xl font-bold font-mono text-slate-800">
                {data?.k_min ?? 50}
              </p>
              <p className="text-xs text-slate-500 mt-1">k-min threshold</p>
            </div>
          </div>

          {/* Range chart */}
          {published.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
              <div className="flex items-center gap-2 mb-1">
                <TrendingUp size={16} className="text-sky-500" />
                <h2 className="font-medium text-slate-800">Compensation range by grade</h2>
              </div>
              <p className="text-xs text-slate-400 mb-5">
                Bars show P25→P75 spread. Hover for details. Values in lakhs (annualised CTC equivalent).
              </p>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748B' }} />
                  <YAxis
                    tickFormatter={v => paiseLakhsLabel(v)}
                    tick={{ fontSize: 11, fill: '#64748B' }}
                    width={48}
                  />
                  <Tooltip content={<BandTooltip />} />
                  {/* Invisible base bar — starts at p25 */}
                  <Bar dataKey="base" stackId="a" fill="transparent" />
                  {/* Visible spread bar — p25 to p75 */}
                  <Bar dataKey="spread" stackId="a" fill="#BAE6FD" radius={[4, 4, 0, 0]}>
                    {chartData.map((_, i) => (
                      <Cell key={i} fill="#BAE6FD" />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div className="flex items-center gap-6 mt-3 justify-center text-xs text-slate-500">
                <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-sky-200 inline-block" /> P25–P75 spread</span>
                <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-sky-600 inline-block" /> Median</span>
              </div>
            </div>
          )}

          {/* Band table */}
          {published.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50">
                    <th className="text-left px-5 py-3 font-medium text-slate-600">Grade</th>
                    <th className="text-left px-5 py-3 font-medium text-slate-600">Department</th>
                    <th className="text-left px-5 py-3 font-medium text-slate-600">Period</th>
                    <th className="text-right px-5 py-3 font-medium text-slate-600">P25</th>
                    <th className="text-right px-5 py-3 font-medium text-slate-600">Median</th>
                    <th className="text-right px-5 py-3 font-medium text-slate-600">P75</th>
                    <th className="text-right px-5 py-3 font-medium text-slate-600">Contributors</th>
                    <th className="text-right px-5 py-3 font-medium text-slate-600">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {published.map(b => (
                    <tr key={`${b.grade}-${b.department}-${b.period}`}
                        className="border-b border-slate-50 hover:bg-slate-50/50">
                      <td className="px-5 py-3 font-medium text-slate-800">{b.grade}</td>
                      <td className="px-5 py-3 text-slate-600">{b.department}</td>
                      <td className="px-5 py-3 text-slate-500">{b.period || '—'}</td>
                      <td className="px-5 py-3 text-right text-emerald-700 font-mono text-xs">
                        {paiseLakhsLabel(b.p25!)}
                      </td>
                      <td className="px-5 py-3 text-right text-sky-700 font-mono text-xs font-semibold">
                        {paiseLakhsLabel(b.p50!)}
                      </td>
                      <td className="px-5 py-3 text-right text-violet-700 font-mono text-xs">
                        {paiseLakhsLabel(b.p75!)}
                      </td>
                      <td className="px-5 py-3 text-right text-slate-400 text-xs">{b.sample_count}</td>
                      <td className="px-5 py-3 text-right text-slate-400 text-xs">{b.data_freshness}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Opt-in stats — always visible so CHRO knows what action to take */}
          {optInStats && (
            <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                  <p className="text-sm font-medium text-slate-700">Employee opt-in status</p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Bands publish automatically once a cohort reaches {data?.k_min ?? 50} contributors
                  </p>
                </div>
                <div className="flex items-center gap-6">
                  <div className="text-center">
                    <p className="text-2xl font-bold font-mono text-emerald-600">{optInStats.opted_in}</p>
                    <p className="text-xs text-slate-400">Opted in</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold font-mono text-amber-500">{optInStats.not_opted_in}</p>
                    <p className="text-xs text-slate-400">Haven't opted in</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold font-mono text-slate-700">{optInStats.opt_in_rate_pct}%</p>
                    <p className="text-xs text-slate-400">Opt-in rate</p>
                  </div>
                </div>
              </div>
              {/* Progress bar */}
              <div className="mt-4 h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-400 rounded-full transition-all"
                  style={{ width: `${Math.min(optInStats.opt_in_rate_pct, 100)}%` }}
                />
              </div>
              {optInStats.not_opted_in > 0 && (
                <p className="text-xs text-slate-500 mt-2">
                  Share this with employees: open PRANA app → menu → Comp Benchmark → toggle on.
                  {optInStats.not_opted_in === 1
                    ? ' Just 1 more opt-in could unlock new bands.'
                    : ` ${optInStats.not_opted_in} employees haven't opted in yet.`}
                </p>
              )}
            </div>
          )}

          {/* Suppressed bands notice */}
          {suppressed.length > 0 && (
            <div className="bg-amber-50 border border-amber-100 rounded-xl p-5">
              <div className="flex items-start gap-3">
                <Lock size={16} className="text-amber-500 mt-0.5 shrink-0" />
                <div>
                  <p className="font-medium text-amber-800 text-sm">
                    {suppressed.length} band{suppressed.length !== 1 ? 's' : ''} waiting for more contributors
                  </p>
                  <p className="text-xs text-amber-700 mt-1">
                    Each needs {data?.k_min ?? 50} opt-ins to publish. Bands unlock automatically — no action needed from you.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {suppressed.map(b => (
                      <span key={`${b.grade}-${b.department}`}
                            className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                        {b.grade} · {b.department} · {b.sample_count}/{data?.k_min ?? 50}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {bands.length === 0 && (
            <div className="text-center py-20 text-slate-400">
              <TrendingUp size={40} className="mx-auto mb-3 opacity-30" />
              <p className="font-medium">No comp bands yet</p>
              <p className="text-sm mt-1 max-w-sm mx-auto">
                Bands appear once employees opt in to sharing their comp data via PRANA.
                Share the employee opt-in guide to get started.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
