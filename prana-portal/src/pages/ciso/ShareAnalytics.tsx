import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link2 } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'
import { tUi } from '@/i18n'

export function ShareAnalytics() {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ['ciso-shares'],
    queryFn: () => api.get('/v1/ciso/shares').then(r => r.data),
    refetchInterval: 60_000,
  })

  const revokeMut = useMutation({
    mutationFn: (shareId: string) => api.post(`/v1/ciso/shares/${shareId}/revoke`, {}).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ciso-shares'] }),
  })

  const stats = [
    { label: tUi('CISO_SHARE_ANALYTICS_ACTIVE_LINKS'), value: data?.active_count ?? '—' },
    { label: tUi('CISO_SHARE_ANALYTICS_ACCESSES_24H'), value: data?.accesses_24h ?? '—' },
    { label: tUi('CISO_SHARE_ANALYTICS_EXPIRED_TODAY'), value: data?.expired_today ?? '—' },
    { label: tUi('CISO_SHARE_ANALYTICS_REVOKED_TODAY'), value: data?.revoked_today ?? '—' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">{tUi('CISO_SHARE_ANALYTICS_TITLE')}</h1>
        <span className="text-xs font-mono text-slate-400">{tUi('CISO_SHARE_ANALYTICS_REFRESH_NOTE')}</span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <Link2 size={18} className="text-indigo-500 mb-2" />
            <p className="text-2xl font-bold font-mono text-slate-800">{s.value}</p>
            <p className="text-xs text-slate-500 mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-medium text-slate-800">{tUi('CISO_SHARE_ANALYTICS_ACTIVE_LINKS')}</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-slate-400 uppercase tracking-wide">
                <th className="px-5 py-3 text-left font-medium">{tUi('CISO_SHARE_ANALYTICS_COL_EMPLOYEE')}</th>
                <th className="px-5 py-3 text-left font-medium">{tUi('CISO_SHARE_ANALYTICS_DOC_TYPE')}</th>
                <th className="px-5 py-3 text-left font-medium">{tUi('CISO_SHARE_ANALYTICS_COL_RECIPIENT')}</th>
                <th className="px-5 py-3 text-right font-medium">{tUi('CISO_SHARE_ANALYTICS_COL_ACCESSES')}</th>
                <th className="px-5 py-3 text-right font-medium">{tUi('CISO_SHARE_ANALYTICS_COL_EXPIRES')}</th>
                <th className="px-5 py-3 text-right font-medium">{tUi('CISO_SHARE_ANALYTICS_COL_ACTION')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {(data?.links ?? []).map((l: any) => (
                <tr key={l.share_id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3 text-slate-700">{l.employee_name}</td>
                  <td className="px-5 py-3 text-slate-500">{l.doc_type?.replace(/_/g, ' ')}</td>
                  <td className="px-5 py-3 text-slate-500">{l.recipient_label ?? tUi('CISO_SHARE_ANALYTICS_UNKNOWN_RECIPIENT')}</td>
                  <td className="px-5 py-3 text-right font-mono text-slate-700">{l.access_count}</td>
                  <td className="px-5 py-3 text-right font-mono text-xs text-slate-400">{fmtDateTime(l.expires_at)}</td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={() => revokeMut.mutate(l.share_id)}
                      disabled={revokeMut.isPending}
                      className="text-xs text-red-600 hover:text-red-800 font-medium"
                    >
                      {tUi('CISO_SHARE_ANALYTICS_REVOKE')}
                    </button>
                  </td>
                </tr>
              ))}
              {!data?.links?.length && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-sm text-slate-400">{tUi('CISO_SHARE_ANALYTICS_NO_LINKS')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
