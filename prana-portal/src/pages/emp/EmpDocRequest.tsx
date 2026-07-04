import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

const DOC_TYPES = ['FORM_16','SALARY_SLIP','RELIEVING_LETTER','EXPERIENCE_LETTER','INCREMENT_LETTER','OFFER_LETTER','APPOINTMENT_LETTER']

export function EmpDocRequest() {
  const [employer, setEmployer]   = useState('')
  const [docType, setDocType]     = useState('')
  const [period, setPeriod]       = useState('')
  const [note, setNote]           = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [toast, setToast]         = useState('')

  const { data: profileData } = useQuery({
    queryKey: ['emp-vault-profile'],
    queryFn: () => api.get('/v1/vault/profile').then(r => r.data),
  })
  const { data: requestsData, refetch } = useQuery({
    queryKey: ['emp-requests'],
    queryFn: () => api.get('/v1/vault/requests').then(r => r.data),
  })

  const employers: any[] = profileData?.employers ?? []
  const requests: any[]  = requestsData?.requests ?? []

  async function send() {
    if (!employer || !docType) return
    setSubmitting(true)
    try {
      const res = await api.post('/v1/vault/requests', { tenant_id: employer, doc_type: docType, period, note })
      setToast(tUi('EMP_DOC_REQUEST_TOAST_SUCCESS', { id: (res.data.doc_request_id ?? '').slice(0,8).toUpperCase() }))
      setDocType(''); setPeriod(''); setNote('')
      refetch()
    } catch { setToast(tUi('EMP_DOC_REQUEST_FAILED')) }
    finally { setSubmitting(false); setTimeout(() => setToast(''), 4000) }
  }

  function fmtDate(d: string | null) {
    if (!d) return '—'
    return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-xl font-semibold text-slate-800 mb-1">{tUi('EMP_DOC_REQUEST_TITLE')}</h1>
      <p className="text-sm text-slate-500 mb-5">{tUi('EMP_DOC_REQUEST_SUB')}</p>

      {toast && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-emerald-50 border border-emerald-200 text-sm text-emerald-700">{toast}</div>
      )}

      <div className="grid gap-4" style={{ gridTemplateColumns: '1.1fr 1fr' }}>
        {/* New Request form */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
          <p className="text-sm font-semibold text-slate-700 mb-1">{tUi('EMP_DOC_REQUEST_NEW_REQUEST')}</p>

          <div>
            <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400 mb-1">{tUi('EMP_DOC_REQUEST_EMPLOYER_LABEL')}</label>
            <select value={employer} onChange={e => setEmployer(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-sky-400 bg-white">
              <option value="">{tUi('EMP_DOC_REQUEST_SELECT_EMPLOYER')}</option>
              {employers.map((e: any) => (
                <option key={e.tenant_id ?? e.id} value={e.tenant_id ?? e.id}>{e.tenant_name ?? e.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400 mb-1">{tUi('EMP_DOC_REQUEST_DOC_TYPE_LABEL')}</label>
            <select value={docType} onChange={e => setDocType(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-sky-400 bg-white">
              <option value="">{tUi('EMP_DOC_REQUEST_SELECT_TYPE')}</option>
              {DOC_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g,' ')}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400 mb-1">{tUi('EMP_DOC_REQUEST_PERIOD_LABEL')}</label>
            <input value={period} onChange={e => setPeriod(e.target.value)}
              placeholder={tUi('EMP_DOC_REQUEST_PERIOD_PLACEHOLDER')}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-sky-400" />
          </div>

          <div>
            <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400 mb-1">{tUi('EMP_DOC_REQUEST_NOTE_LABEL')}</label>
            <textarea value={note} onChange={e => setNote(e.target.value)} rows={2}
              placeholder={tUi('EMP_DOC_REQUEST_NOTE_PLACEHOLDER')}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-sky-400 resize-none" />
          </div>

          <button onClick={send} disabled={submitting || !employer || !docType}
            className="w-full px-4 py-2.5 bg-sky-600 text-white rounded-lg text-sm font-medium hover:bg-sky-700 disabled:opacity-40">
            {submitting ? tUi('EMP_DOC_REQUEST_SENDING') : tUi('EMP_DOC_REQUEST_SEND_BTN')}
          </button>

          <p className="text-[10px] text-slate-400 leading-4">
            {tUi('EMP_DOC_REQUEST_FOOTER_NOTE')}
          </p>
        </div>

        {/* Request History */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <p className="text-sm font-semibold text-slate-700 mb-3">{tUi('EMP_DOC_REQUEST_HISTORY_TITLE')}</p>
          {requests.length === 0 ? (
            <p className="text-sm text-slate-400">{tUi('EMP_DOC_REQUEST_NONE')}</p>
          ) : requests.map((r: any, i: number) => (
            <div key={i} className={`p-3 rounded-lg mb-2 ${r.status === 'FULFILLED' ? 'bg-white border border-slate-200' : 'border border-amber-200'}`}
              style={r.status !== 'FULFILLED' ? { background: 'rgba(245,158,11,0.03)' } : {}}>
              <div className="flex items-start justify-between gap-2">
                <p className="text-xs font-semibold text-slate-800">{r.doc_type?.replace(/_/g,' ')} · {r.period ?? '—'}</p>
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0 ${
                  r.status === 'FULFILLED' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'
                }`}>
                  {r.status === 'FULFILLED' ? tUi('EMP_DOC_REQUEST_FULFILLED') : `${tUi('EMP_DOC_REQUEST_PENDING_PREFIX')} · ${Math.floor((Date.now() - new Date(r.requested_at ?? 0).getTime()) / 86400000)}d`}
                </span>
              </div>
              <p className="text-[10px] text-slate-400 mt-1">
                {r.tenant_name} · {tUi('EMP_DOC_REQUEST_SENT_PREFIX')} {fmtDate(r.requested_at)}{r.fulfilled_at ? ` · ${tUi('EMP_DOC_REQUEST_FULFILLED')} ${fmtDate(r.fulfilled_at)}` : ''}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
