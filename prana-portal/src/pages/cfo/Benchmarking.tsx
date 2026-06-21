import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function Benchmarking() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['cfo-benchmarking'],
    queryFn: () => api.get('/v1/cfo/benchmarking').then(r => r.data),
  })

  if (isLoading) return (
    <div className="space-y-6 animate-pulse">
      <div className="h-6 w-40 bg-slate-200 rounded" />
      <div className="h-72 bg-slate-100 rounded-xl" />
    </div>
  )
  if (isError) return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-400">
      <p className="text-sm">Failed to load benchmarking data.</p>
      <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">Retry</button>
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Benchmarking</h1>
        <p className="text-xs text-indigo-600 bg-indigo-50 rounded-md px-2 py-1 mt-1 inline-block">
          Market data shown as P25 / P50 / P75 indices — no individual figures
        </p>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-medium text-slate-800">Market percentile vs org median by role</h2>
          <p className="text-xs text-slate-400 mt-0.5">Source: aggregated PRANA platform data · minimum cohort 30</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-slate-400 uppercase tracking-wide">
                <th className="px-5 py-3 text-left font-medium">Role category</th>
                <th className="px-5 py-3 text-right font-medium">Market P25</th>
                <th className="px-5 py-3 text-right font-medium">Market P50</th>
                <th className="px-5 py-3 text-right font-medium">Market P75</th>
                <th className="px-5 py-3 text-right font-medium">Org median</th>
                <th className="px-5 py-3 text-right font-medium">Position</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {(data?.rows ?? []).map((row: any) => (
                <tr key={row.role_category} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3 font-medium text-slate-700">{row.role_category}</td>
                  <td className="px-5 py-3 text-right font-mono text-slate-500">{row.p25_label}</td>
                  <td className="px-5 py-3 text-right font-mono text-slate-700">{row.p50_label}</td>
                  <td className="px-5 py-3 text-right font-mono text-slate-500">{row.p75_label}</td>
                  <td className="px-5 py-3 text-right font-mono font-semibold text-indigo-700">{row.org_median_label}</td>
                  <td className="px-5 py-3 text-right">
                    <PositionBadge position={row.position} />
                  </td>
                </tr>
              ))}
              {!data?.rows?.length && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-sm text-slate-400">
                    No benchmarking data available. Requires minimum cohort of 30.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 text-xs text-amber-700">
        Benchmarking data is derived from aggregated PRANA platform documents. Cohort minimum of 30 is enforced.
        No individual employee data is included in market comparisons.
      </div>
    </div>
  )
}

function PositionBadge({ position }: { position: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    BELOW_P25: { label: 'Below P25', cls: 'bg-red-100 text-red-700' },
    P25_P50:   { label: 'P25–P50',  cls: 'bg-amber-100 text-amber-700' },
    P50_P75:   { label: 'P50–P75',  cls: 'bg-emerald-100 text-emerald-700' },
    ABOVE_P75: { label: 'Above P75', cls: 'bg-sky-100 text-sky-700' },
  }
  const s = map[position] ?? { label: position ?? '—', cls: 'bg-slate-100 text-slate-500' }
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${s.cls}`}>{s.label}</span>
}
