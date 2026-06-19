import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Download } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

const ACTION_TYPES = ['ALL','DOC_OPEN','DOC_DELETE','DOC_PUSH','USER_CREATE','ELEVATION','EXCEPTION_RESOLVE']

export function OaActivityAudit() {
  const [actionType, setActionType] = useState('ALL')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)

  const { data, isLoading } = useQuery({
    queryKey: ['ciso-oa-audit', actionType, page],
    queryFn: () => api.get('/v1/ciso/oa-audit', {
      params: { action_type: actionType === 'ALL' ? undefined : actionType, offset: page * 50, limit: 50 },
    }).then(r => r.data),
  })

  async function exportPdf() {
    const res = await api.get('/v1/ciso/oa-audit/export', { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url; a.download = 'oa_audit_export.pdf'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-slate-800">OA Activity Audit</h1>
        <button onClick={exportPdf}
                className="flex items-center gap-2 px-4 py-2 border border-slate-200
                           rounded-lg text-sm font-medium text-slate-600 hover:bg-canvas2">
          <Download size={14}/> Export signed PDF
        </button>
      </div>

      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={e => setSearch(e.target.value)}
                 placeholder="Search by user or action…"
                 className="w-full pl-9 pr-4 py-2.5 border border-slate-200 rounded-lg text-sm
                            focus:outline-none focus:ring-2 focus:ring-red-400" />
        </div>
        <select value={actionType} onChange={e => { setActionType(e.target.value); setPage(0) }}
                className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white
                           focus:outline-none focus:ring-2 focus:ring-red-400">
          {ACTION_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g,' ')}</option>)}
        </select>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-5 py-3 font-medium">Actor</th>
              <th className="text-left px-5 py-3 font-medium">Action</th>
              <th className="text-left px-5 py-3 font-medium">Resource</th>
              <th className="text-left px-5 py-3 font-medium">IP</th>
              <th className="text-left px-5 py-3 font-medium">Timestamp</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading && (
              <tr><td colSpan={5} className="px-5 py-8 text-center text-slate-400">Loading…</td></tr>
            )}
            {data?.events?.map((e: any, i: number) => (
              <tr key={i} className="hover:bg-canvas2">
                <td className="px-5 py-3">
                  <p className="text-sm font-medium text-slate-800">{e.actor_name}</p>
                  <p className="text-xs text-slate-400 font-mono">{e.actor_role}</p>
                </td>
                <td className="px-5 py-3">
                  <span className={`badge ${
                    e.action_type?.includes('DELETE') ? 'badge-red' :
                    e.action_type?.includes('ELEVATION') ? 'badge-amber' : 'badge-muted'
                  }`}>{e.action_type?.replace(/_/g,' ')}</span>
                </td>
                <td className="px-5 py-3 font-mono text-xs text-slate-500 truncate max-w-[180px]">
                  {e.resource_id ?? '—'}
                </td>
                <td className="px-5 py-3 font-mono text-xs text-slate-500">{e.ip_address}</td>
                <td className="px-5 py-3 text-xs text-slate-400">{fmtDateTime(e.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
