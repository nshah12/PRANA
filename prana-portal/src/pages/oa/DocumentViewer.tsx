import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, Eye, Trash2, Search } from 'lucide-react'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { fmtDate } from '@/lib/utils'
import { PipelineStatusBadge } from './Dashboard'

export function DocumentViewer() {
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'oa_admin'
  const [search, setSearch] = useState('')
  const [docType, setDocType] = useState('')
  const [page] = useState(0)
  const limit = 20

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['documents', docType, page],
    queryFn: () => api.get('/ingest/documents', {
      params: { doc_type: docType || undefined, pipeline_status: 'ROUTED', limit, offset: page * limit },
    }).then(r => r.data),
  })

  async function openDoc(docId: string) {
    // Opens in new tab — every view is logged server-side
    window.open(`/api/vault/documents/${docId}`, '_blank')
  }

  async function deleteDoc(docId: string) {
    if (!confirm('Mark this document as deleted? This cannot be undone.')) return
    await api.delete(`/ingest/documents/${docId}`)
    refetch()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Document Viewer</h1>
          <p className="text-xs text-amber-600 bg-amber-50 rounded-md px-2 py-1 mt-1 inline-block">
            Every document open is logged immutably with your identity and timestamp
          </p>
        </div>
      </div>

      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={e => setSearch(e.target.value)}
                 placeholder="Search documents…"
                 className="w-full pl-9 pr-4 py-2.5 border border-slate-200 rounded-lg text-sm
                            focus:outline-none focus:ring-2 focus:ring-violet-500" />
        </div>
        <select value={docType} onChange={e => setDocType(e.target.value)}
                className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white
                           focus:outline-none focus:ring-2 focus:ring-violet-500">
          <option value="">All types</option>
          {['SALARY_SLIP','FORM_16','OFFER_LETTER','APPOINTMENT_LETTER',
            'EXPERIENCE_LETTER','RELIEVING_LETTER','JOINING_LETTER','PF_ACKNOWLEDGEMENT']
            .map(t => <option key={t} value={t}>{t.replace(/_/g,' ')}</option>)}
        </select>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-5 py-3 font-medium">Document</th>
              <th className="text-left px-5 py-3 font-medium">Period</th>
              <th className="text-left px-5 py-3 font-medium">Status</th>
              <th className="text-left px-5 py-3 font-medium">Pushed</th>
              <th className="text-left px-5 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading && (
              <tr><td colSpan={5} className="px-5 py-8 text-center text-slate-400">Loading…</td></tr>
            )}
            {data?.map((doc: any) => (
              <tr key={doc.document_id} className="hover:bg-canvas2">
                <td className="px-5 py-3">
                  <div className="flex items-center gap-3">
                    <FileText size={16} className="text-slate-400 flex-shrink-0" />
                    <span className="font-medium text-slate-700">
                      {doc.doc_type.replace(/_/g, ' ')}
                    </span>
                  </div>
                </td>
                <td className="px-5 py-3 font-mono text-xs text-slate-500">{doc.doc_period ?? '—'}</td>
                <td className="px-5 py-3"><PipelineStatusBadge status={doc.pipeline_status} /></td>
                <td className="px-5 py-3 text-slate-400 text-xs">{fmtDate(doc.pushed_at)}</td>
                <td className="px-5 py-3">
                  <div className="flex gap-2">
                    <button onClick={() => openDoc(doc.document_id)}
                            className="flex items-center gap-1 text-xs text-violet-600
                                       hover:underline font-medium">
                      <Eye size={13}/> View
                    </button>
                    {isAdmin && (
                      <button onClick={() => deleteDoc(doc.document_id)}
                              className="flex items-center gap-1 text-xs text-red-500
                                         hover:underline font-medium">
                        <Trash2 size={13}/> Delete
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
