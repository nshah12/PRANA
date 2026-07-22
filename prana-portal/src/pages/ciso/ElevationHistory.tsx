import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ShieldCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'
import { tUi } from '@/i18n'

const STATUS_STYLE: Record<string, string> = {
  PENDING:  'bg-amber-50 text-amber-700',
  APPROVED: 'bg-emerald-50 text-emerald-700',
  DENIED:   'bg-red-50 text-red-700',
  ACTIVE:   'bg-indigo-50 text-indigo-700',
  EXPIRED:  'bg-slate-100 text-slate-500',
  ENDED:    'bg-slate-100 text-slate-500',
}

export function ElevationHistory() {
  const [page, setPage] = useState(0)
  const PAGE = 50

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['ciso-elevations', page],
    queryFn: () => api.get('/v1/ciso/elevations', {
      params: { offset: page * PAGE, limit: PAGE },
    }).then(r => r.data),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">{tUi('CISO_ELEVATION_HIST_TITLE')}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{tUi('CISO_ELEVATION_HIST_SUB')}</p>
        </div>
        <span className="text-xs font-mono text-slate-400">{data?.total ?? 0} total</span>
      </div>

      {isLoading && (
        <div className="space-y-2 animate-pulse">
          {[...Array(5)].map((_, i) => <div key={i} className="h-16 bg-slate-100 rounded-xl" />)}
        </div>
      )}
      {isError && (
        <div className="text-center py-16 text-slate-400">
          <p className="text-sm">{tUi('CISO_ELEVATION_HIST_LOAD_FAILED')}</p>
          <button onClick={() => refetch()} className="mt-2 text-xs text-red-600 hover:underline">{tUi('CFO_ATTRITION_RETRY')}</button>
        </div>
      )}

      {!isLoading && !isError && data?.items?.length === 0 && (
        <div className="bg-white rounded-xl border border-slate-100 p-16 text-center">
          <ShieldCheck size={32} className="text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 font-medium">{tUi('CISO_ELEVATION_HIST_NONE_TITLE')}</p>
          <p className="text-xs text-slate-400 mt-1">{tUi('CISO_ELEVATION_HIST_NONE_SUB')}</p>
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        {data?.items?.length > 0 && (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
              <tr>
                <th className="text-left px-5 py-3 font-medium">{tUi('CISO_ELEVATION_HIST_COL_REQUESTOR')}</th>
                <th className="text-left px-5 py-3 font-medium">{tUi('CISO_ELEVATION_HIST_COL_APPROVER')}</th>
                <th className="text-left px-5 py-3 font-medium">{tUi('CISO_ELEVATION_HIST_COL_REASON')}</th>
                <th className="text-left px-5 py-3 font-medium">{tUi('CISO_ELEVATION_HIST_COL_DURATION')}</th>
                <th className="text-left px-5 py-3 font-medium">{tUi('CISO_ELEVATION_HIST_COL_STATUS')}</th>
                <th className="text-left px-5 py-3 font-medium">{tUi('CISO_ELEVATION_HIST_COL_REQUESTED')}</th>
                <th className="text-left px-5 py-3 font-medium">{tUi('CISO_ELEVATION_HIST_COL_EXPIRES')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {data.items.map((row: any) => (
                <tr key={row.elevation_id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3">
                    <p className="font-medium text-slate-800">{row.requestor_name ?? '—'}</p>
                    <p className="text-xs text-slate-400">{row.requestor_email ?? ''}</p>
                  </td>
                  <td className="px-5 py-3 text-slate-600">{row.approver_name ?? '—'}</td>
                  <td className="px-5 py-3 text-slate-500 max-w-[200px] truncate">{row.reason ?? '—'}</td>
                  <td className="px-5 py-3 font-mono text-xs text-slate-600">{row.duration_hours ? `${row.duration_hours}h` : '—'}</td>
                  <td className="px-5 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[row.status] ?? 'bg-slate-100 text-slate-600'}`}>
                      {row.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs text-slate-400">{fmtDateTime(row.requested_at)}</td>
                  <td className="px-5 py-3 text-xs text-slate-400">{fmtDateTime(row.expires_at) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {(data?.total ?? 0) > PAGE && (
        <div className="flex justify-between items-center text-sm">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                  className="px-4 py-2 border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50">
            {tUi('CISO_ELEVATION_HIST_PREVIOUS')}
          </button>
          <span className="text-slate-400 text-xs">Page {page + 1} of {Math.ceil((data?.total ?? 0) / PAGE)}</span>
          <button onClick={() => setPage(p => p + 1)}
                  disabled={(page + 1) * PAGE >= (data?.total ?? 0)}
                  className="px-4 py-2 border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50">
            Next
          </button>
        </div>
      )}
    </div>
  )
}
