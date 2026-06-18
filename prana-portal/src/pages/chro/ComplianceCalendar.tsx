import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Bell, BookOpen } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDate } from '@/lib/utils'

const STATUS_STYLE: Record<string, string> = {
  PENDING:     'bg-slate-100 text-slate-600',
  IN_PROGRESS: 'bg-sky-50 text-sky-700',
  COMPLETE:    'bg-emerald-50 text-emerald-700',
  OVERDUE:     'bg-red-50 text-red-700',
  WAIVED:      'bg-slate-50 text-slate-400',
}

export function ComplianceCalendar() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['chro-compliance'],
    queryFn: () => api.get('/v1/chro/compliance').then(r => r.data),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Compliance Calendar</h1>
          <p className="text-sm text-slate-500 mt-0.5">Statutory deadlines — Labour law, DPDP Act, Income Tax Act</p>
        </div>
        <div className="flex items-center gap-3">
          {(data?.overdue ?? 0) > 0 && (
            <span className="flex items-center gap-1.5 text-xs font-semibold text-red-700 bg-red-50 border border-red-200 px-3 py-1.5 rounded-full">
              <AlertCircle size={12}/> {data.overdue} overdue
            </span>
          )}
          <span className="text-xs text-slate-400">{data?.total ?? 0} obligations</span>
        </div>
      </div>

      {isLoading && (
        <div className="space-y-2 animate-pulse">
          {[...Array(5)].map((_, i) => <div key={i} className="h-16 bg-slate-100 rounded-xl" />)}
        </div>
      )}
      {isError && (
        <div className="text-center py-16 text-slate-400">
          <p className="text-sm">Failed to load compliance calendar.</p>
          <button onClick={() => refetch()} className="mt-2 text-xs text-red-600 hover:underline">Retry</button>
        </div>
      )}

      {!isLoading && !isError && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
              <tr>
                <th className="text-left px-5 py-3 font-medium">Obligation / Statutory reference</th>
                <th className="text-left px-5 py-3 font-medium">Period</th>
                <th className="text-left px-5 py-3 font-medium">Deadline</th>
                <th className="text-left px-5 py-3 font-medium">Days</th>
                <th className="text-left px-5 py-3 font-medium">Coverage</th>
                <th className="text-left px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {data?.items?.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-12 text-center text-slate-400">
                    No compliance obligations configured. Contact Platform Admin to seed statutory calendar.
                  </td>
                </tr>
              )}
              {data?.items?.map((item: any) => {
                const days = Math.ceil((new Date(item.deadline).getTime() - Date.now()) / 86_400_000)
                const overdue = item.is_overdue
                return (
                  <tr key={item.obligation_id} className={`hover:bg-slate-50/50 ${overdue ? 'bg-red-50/30' : ''}`}>
                    <td className="px-5 py-3">
                      <p className="font-medium text-slate-800">{item.obligation_name}</p>
                      {item.statutory_ref && (
                        <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-1">
                          <BookOpen size={10}/> {item.statutory_ref}
                        </p>
                      )}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-500">{item.period ?? '—'}</td>
                    <td className="px-5 py-3 text-slate-600">{fmtDate(item.deadline)}</td>
                    <td className="px-5 py-3">
                      <span className={`font-mono text-xs font-bold ${
                        overdue ? 'text-red-600' : days < 14 ? 'text-amber-600' : 'text-emerald-600'
                      }`}>
                        {overdue ? `${Math.abs(days)}d overdue` : `${days}d`}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      {item.total_employees > 0 ? (
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${item.completion_pct >= 90 ? 'bg-emerald-500' : item.completion_pct >= 70 ? 'bg-amber-500' : 'bg-red-500'}`}
                              style={{ width: `${item.completion_pct}%` }}
                            />
                          </div>
                          <span className="text-xs font-mono text-slate-600">{item.completion_pct}%</span>
                        </div>
                      ) : <span className="text-xs text-slate-300">—</span>}
                    </td>
                    <td className="px-5 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[item.status] ?? 'bg-slate-100 text-slate-600'}`}>
                        {item.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right">
                      {overdue && (
                        <button className="flex items-center gap-1 text-xs text-amber-600 font-medium hover:underline whitespace-nowrap">
                          <Bell size={11}/> Alert operator
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
