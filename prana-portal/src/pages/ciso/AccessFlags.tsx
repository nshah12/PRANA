import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Flag, FlagOff } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function AccessFlags() {
  const qc = useQueryClient()
  const [page, setPage] = useState(0)
  const PAGE = 50

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['ciso-access-flags', page],
    queryFn: () => api.get('/v1/ciso/access-flags', {
      params: { offset: page * PAGE, limit: PAGE },
    }).then(r => r.data),
  })

  const unflagMut = useMutation({
    mutationFn: (access_id: string) =>
      api.patch(`/v1/ciso/access-flags/${access_id}`, { is_flagged: false }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ciso-access-flags'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Flagged Access Log</h1>
          <p className="text-sm text-slate-500 mt-0.5">Document accesses flagged for review. Full IP visible to CISO only.</p>
        </div>
        <span className="text-xs font-mono text-slate-400">{data?.total ?? 0} flagged entries</span>
      </div>

      {isLoading && (
        <div className="space-y-2 animate-pulse">
          {[...Array(5)].map((_, i) => <div key={i} className="h-14 bg-slate-100 rounded-xl" />)}
        </div>
      )}
      {isError && (
        <div className="text-center py-16 text-slate-400">
          <p className="text-sm">Failed to load flagged access log.</p>
          <button onClick={() => refetch()} className="mt-2 text-xs text-red-600 hover:underline">Retry</button>
        </div>
      )}

      {!isLoading && !isError && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
              <tr>
                <th className="text-left px-5 py-3 font-medium">Doc type / Period</th>
                <th className="text-left px-5 py-3 font-medium">Channel</th>
                <th className="text-left px-5 py-3 font-medium">IP address</th>
                <th className="text-left px-5 py-3 font-medium">Flag reason</th>
                <th className="text-left px-5 py-3 font-medium">Accessed</th>
                <th className="px-5 py-3 font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {data?.items?.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-slate-400">No flagged access entries.</td>
                </tr>
              )}
              {data?.items?.map((row: any) => (
                <tr key={row.access_id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3">
                    <p className="font-medium text-slate-800">{row.doc_type?.replace(/_/g, ' ') ?? '—'}</p>
                    <p className="text-xs text-slate-400">{row.doc_period ?? '—'}</p>
                  </td>
                  <td className="px-5 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                      row.access_channel === 'SHARE_LINK' ? 'bg-amber-50 text-amber-700' :
                      row.access_channel === 'MOBILE'     ? 'bg-sky-50 text-sky-700' :
                                                            'bg-slate-100 text-slate-600'
                    }`}>{row.access_channel ?? '—'}</span>
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-slate-700">{row.ip_address ?? '—'}</td>
                  <td className="px-5 py-3 text-xs text-red-700">{row.flag_reason ?? '—'}</td>
                  <td className="px-5 py-3 text-xs text-slate-400">{fmtDateTime(row.accessed_at)}</td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={() => unflagMut.mutate(row.access_id)}
                      disabled={unflagMut.isPending}
                      className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 border border-slate-200 px-2.5 py-1 rounded-lg hover:bg-slate-50"
                    >
                      <FlagOff size={11} /> Unflag
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {(data?.total ?? 0) > PAGE && (
        <div className="flex justify-between items-center text-sm">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                  className="px-4 py-2 border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50">
            Previous
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
