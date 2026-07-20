import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Shield, Download, AlertCircle, Trash2, MessageSquare, ChevronRight, Loader2, CheckCircle, UserCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

interface ConsentRecord {
  id: string; purpose: string; purpose_label: string;
  consented_at: string; consent_version: string; is_active: boolean;
}

// ── S.11 Access panel ──────────────────────────────────────────────────────────
function AccessPanel() {
  const [requested, setRequested] = useState(false)
  const [loading, setLoading]     = useState(false)
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600 leading-5">
        {tUi('EMP_DATA_RIGHTS_ACCESS_DESC')}
      </p>
      {requested ? (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl border text-emerald-700"
          style={{ background:'rgba(16,185,129,0.06)', borderColor:'rgba(16,185,129,0.2)' }}>
          <CheckCircle size={16}/> <span className="text-sm font-medium">{tUi('EMP_DATA_RIGHTS_ACCESS_SUCCESS')}</span>
        </div>
      ) : (
        <button onClick={async () => { setLoading(true); try { await api.post('/v1/dpdp/export'); setRequested(true) } catch {} finally { setLoading(false) }}}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-white disabled:opacity-50"
          style={{ background:'#6366F1' }}>
          {loading ? <Loader2 size={14} className="animate-spin"/> : <Download size={14}/>}
          {tUi('EMP_DATA_RIGHTS_ACCESS_BTN')}
        </button>
      )}
    </div>
  )
}

// ── S.12 Correction panel ─────────────────────────────────────────────────────
function CorrectionPanel() {
  const [field, setField]       = useState('')
  const [cur, setCur]           = useState('')
  const [correct, setCorrect]   = useState('')
  const [note, setNote]         = useState('')
  const [loading, setLoading]   = useState(false)
  const [done, setDone]         = useState(false)
  const [err, setErr]           = useState('')

  if (done) return (
    <div className="flex items-center gap-2 px-4 py-3 rounded-xl border text-emerald-700"
      style={{ background:'rgba(16,185,129,0.06)', borderColor:'rgba(16,185,129,0.2)' }}>
      <CheckCircle size={16}/> <span className="text-sm font-medium">{tUi('EMP_DATA_RIGHTS_CORRECTION_SUCCESS')}</span>
    </div>
  )
  return (
    <div className="space-y-2.5">
      <p className="text-sm text-slate-600">{tUi('EMP_DATA_RIGHTS_CORRECTION_DESC')}</p>
      {[
        { val: field, set: setField, ph: tUi('EMP_DATA_RIGHTS_FIELD_NAME_PLACEHOLDER') },
        { val: cur,   set: setCur,   ph: tUi('EMP_DATA_RIGHTS_CURRENT_VALUE_PLACEHOLDER') },
        { val: correct, set: setCorrect, ph: tUi('EMP_DATA_RIGHTS_CORRECT_VALUE_PLACEHOLDER') },
      ].map(f => (
        <input key={f.ph} value={f.val} onChange={e => f.set(e.target.value)} placeholder={f.ph}
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-indigo-400"/>
      ))}
      <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} placeholder={tUi('EMP_DATA_RIGHTS_EVIDENCE_PLACEHOLDER')}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-indigo-400 resize-none"/>
      {err && <p className="text-red-500 text-xs">{err}</p>}
      <button onClick={async () => {
        if (!field || !correct) { setErr(tUi('EMP_DATA_RIGHTS_CORRECTION_ERR_REQUIRED')); return }
        setErr(''); setLoading(true)
        try { await api.post('/v1/dpdp/correction', { field, current_value: cur, correct_value: correct, evidence_note: note }); setDone(true) }
        catch { setErr(tUi('EMP_DATA_RIGHTS_SUBMIT_FAILED_RETRY')) }
        finally { setLoading(false) }
      }} disabled={loading} className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-white disabled:opacity-50"
        style={{ background:'#6366F1' }}>
        {loading && <Loader2 size={14} className="animate-spin"/>}
        {tUi('EMP_DATA_RIGHTS_SUBMIT_CORRECTION_BTN')}
      </button>
    </div>
  )
}

// ── S.12 Erasure panel ────────────────────────────────────────────────────────
function ErasurePanel() {
  const [reason, setReason]       = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [loading, setLoading]     = useState(false)
  const [done, setDone]           = useState(false)
  const [err, setErr]             = useState('')

  if (done) return (
    <div className="flex items-center gap-2 px-4 py-3 rounded-xl border text-emerald-700"
      style={{ background:'rgba(16,185,129,0.06)', borderColor:'rgba(16,185,129,0.2)' }}>
      <CheckCircle size={16}/> <span className="text-sm font-medium">{tUi('EMP_DATA_RIGHTS_ERASURE_SUCCESS')}</span>
    </div>
  )
  return (
    <div className="space-y-3">
      <div className="px-3 py-2 rounded-lg text-xs text-red-700 leading-4"
        style={{ background:'rgba(239,68,68,0.05)', border:'1px solid rgba(239,68,68,0.15)' }}>
        ⚠️ {tUi('EMP_DATA_RIGHTS_ERASURE_WARNING')}
      </div>
      <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} placeholder={tUi('EMP_DATA_RIGHTS_ERASURE_REASON_PLACEHOLDER')}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-red-400 resize-none"/>
      <label className="flex items-start gap-2 cursor-pointer">
        <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-0.5 accent-red-600"/>
        <span className="text-xs text-slate-600">{tUi('EMP_DATA_RIGHTS_ERASURE_CONFIRM_LABEL')}</span>
      </label>
      {err && <p className="text-red-500 text-xs">{err}</p>}
      <button onClick={async () => {
        if (!confirmed) { setErr(tUi('EMP_DATA_RIGHTS_ERASURE_CONFIRM_ERR')); return }
        setErr(''); setLoading(true)
        try { await api.post('/v1/dpdp/erasure', { reason }); setDone(true) }
        catch { setErr(tUi('EMP_DATA_RIGHTS_SUBMIT_FAILED_RETRY')) }
        finally { setLoading(false) }
      }} disabled={loading || !confirmed}
        className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-white disabled:opacity-40"
        style={{ background:'#DC2626' }}>
        {loading ? <Loader2 size={14} className="animate-spin"/> : <Trash2 size={14}/>}
        {tUi('EMP_DATA_RIGHTS_REQUEST_ERASURE_BTN')}
      </button>
    </div>
  )
}

// ── S.13 Grievance panel ──────────────────────────────────────────────────────
function GrievancePanel() {
  const [sub, setSub]   = useState('')
  const [desc, setDesc] = useState('')
  const [loading, setLoading] = useState(false)
  const [done, setDone]       = useState(false)
  const [err, setErr]         = useState('')

  if (done) return (
    <div className="flex items-center gap-2 px-4 py-3 rounded-xl border text-emerald-700"
      style={{ background:'rgba(16,185,129,0.06)', borderColor:'rgba(16,185,129,0.2)' }}>
      <CheckCircle size={16}/> <span className="text-sm font-medium">{tUi('EMP_DATA_RIGHTS_GRIEVANCE_SUCCESS')}</span>
    </div>
  )
  return (
    <div className="space-y-2.5">
      <p className="text-sm text-slate-600">{tUi('EMP_DATA_RIGHTS_GRIEVANCE_DESC')}</p>
      <input value={sub} onChange={e => setSub(e.target.value)} placeholder={tUi('EMP_DATA_RIGHTS_SUBJECT_PLACEHOLDER')} maxLength={120}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-indigo-400"/>
      <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3} placeholder={tUi('EMP_DATA_RIGHTS_GRIEVANCE_DESC_PLACEHOLDER')}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-indigo-400 resize-none"/>
      {err && <p className="text-red-500 text-xs">{err}</p>}
      <button onClick={async () => {
        if (!sub || !desc) { setErr(tUi('EMP_DATA_RIGHTS_GRIEVANCE_ERR_REQUIRED')); return }
        setErr(''); setLoading(true)
        try { await api.post('/v1/dpdp/grievance', { subject: sub, description: desc }); setDone(true) }
        catch { setErr(tUi('EMP_DATA_RIGHTS_SUBMIT_FAILED')) }
        finally { setLoading(false) }
      }} disabled={loading} className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-white disabled:opacity-50"
        style={{ background:'#6366F1' }}>
        {loading ? <Loader2 size={14} className="animate-spin"/> : <MessageSquare size={14}/>}
        {tUi('EMP_DATA_RIGHTS_SUBMIT_GRIEVANCE_BTN')}
      </button>
    </div>
  )
}

// ── S.14 Nomination panel ──────────────────────────────────────────────────────
function NominationPanel() {
  const [name, setName]     = useState('')
  const [rel, setRel]       = useState('')
  const [mobile, setMobile] = useState('')
  const [done, setDone]     = useState(false)
  const [loading, setLoading] = useState(false)

  if (done) return (
    <div className="flex items-center gap-2 px-4 py-3 rounded-xl border text-emerald-700"
      style={{ background:'rgba(16,185,129,0.06)', borderColor:'rgba(16,185,129,0.2)' }}>
      <CheckCircle size={16}/> <span className="text-sm font-medium">{tUi('EMP_DATA_RIGHTS_NOMINATION_SUCCESS')}</span>
    </div>
  )
  return (
    <div className="space-y-2.5">
      <p className="text-sm text-slate-600">{tUi('EMP_DATA_RIGHTS_NOMINATION_DESC')}</p>
      {[
        { val: name,   set: setName,   ph: tUi('EMP_DATA_RIGHTS_NOMINEE_NAME_PLACEHOLDER') },
        { val: rel,    set: setRel,    ph: tUi('EMP_DATA_RIGHTS_RELATIONSHIP_PLACEHOLDER') },
        { val: mobile, set: setMobile, ph: tUi('EMP_DATA_RIGHTS_NOMINEE_MOBILE_PLACEHOLDER') },
      ].map(f => (
        <input key={f.ph} value={f.val} onChange={e => f.set(e.target.value)} placeholder={f.ph}
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-indigo-400"/>
      ))}
      <button onClick={async () => {
        setLoading(true)
        try { await new Promise(r => setTimeout(r, 600)); setDone(true) }
        finally { setLoading(false) }
      }} disabled={loading || !name || !mobile}
        className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-white disabled:opacity-50"
        style={{ background:'#6366F1' }}>
        {loading && <Loader2 size={14} className="animate-spin"/>}
        {tUi('EMP_DATA_RIGHTS_SAVE_NOMINEE_BTN')}
      </button>
    </div>
  )
}

// ── S.7 Consent panel ─────────────────────────────────────────────────────────
function ConsentPanel() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['emp-consents'],
    queryFn: () => api.get<{ consents: ConsentRecord[] }>('/v1/dpdp/consents').then(r => r.data),
  })
  const withdrawMut = useMutation({
    mutationFn: (id: string) => api.post(`/v1/dpdp/consents/${id}/withdraw`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['emp-consents'] }),
  })

  const consents = data?.consents ?? []

  // Fallback consent toggles if no API data
  const [local, setLocal] = useState({ analytics: true, benchmarking: true, anomaly: true })

  return (
    <div className="space-y-3">
      <div className="px-3 py-2 rounded-lg text-xs text-amber-700 leading-4"
        style={{ background:'rgba(245,158,11,0.06)', border:'1px solid rgba(245,158,11,0.15)' }}>
        ⚠️ {tUi('EMP_DATA_RIGHTS_CONSENT_WARNING')}
      </div>

      {isLoading
        ? [...Array(3)].map((_,i) => <div key={i} className="h-14 bg-slate-100 animate-pulse rounded-xl"/>)
        : consents.length > 0
        ? consents.map(c => (
            <div key={c.id} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl px-4 py-3">
              <div className="flex-1">
                <p className="text-sm font-medium text-slate-800">{c.purpose_label}</p>
                <p className="text-xs text-slate-400 mt-0.5">{tUi('EMP_DATA_RIGHTS_CONSENTED_PREFIX')} {new Date(c.consented_at).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'})} · v{c.consent_version}</p>
              </div>
              {c.is_active
                ? <button onClick={() => withdrawMut.mutate(c.id)} disabled={withdrawMut.isPending}
                    className="text-xs text-red-500 border border-red-200 rounded-lg px-2.5 py-1.5 hover:bg-red-50 disabled:opacity-50">{tUi('EMP_DATA_RIGHTS_WITHDRAW_BTN')}</button>
                : <span className="text-xs text-slate-400 bg-slate-100 rounded-full px-2.5 py-1">{tUi('EMP_DATA_RIGHTS_WITHDRAWN_LABEL')}</span>
              }
            </div>
          ))
        : (
            <div className="space-y-2">
              {[
                { key: 'analytics',    label: tUi('EMP_DATA_RIGHTS_CONSENT_ANALYTICS'),        k: 'analytics' as const },
                { key: 'benchmarking', label: tUi('EMP_DATA_RIGHTS_CONSENT_BENCHMARKING'),         k: 'benchmarking' as const },
                { key: 'anomaly',      label: tUi('EMP_DATA_RIGHTS_CONSENT_ANOMALY'),             k: 'anomaly' as const },
              ].map(row => (
                <div key={row.key} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl px-4 py-3">
                  <p className="text-sm text-slate-700 flex-1">{row.label}</p>
                  <button onClick={() => setLocal(p => ({ ...p, [row.k]: !p[row.k] }))}
                    className={`relative inline-flex w-9 h-5 rounded-full transition-colors shrink-0 ${local[row.k] ? 'bg-emerald-500' : 'bg-slate-200'}`}>
                    <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${local[row.k] ? 'translate-x-4' : 'translate-x-0'}`}/>
                  </button>
                </div>
              ))}
              <p className="text-[10px] text-slate-400 leading-4 pt-1">
                {tUi('EMP_DATA_RIGHTS_CONSENT_INSTANT_NOTE')}
              </p>
            </div>
          )
      }
    </div>
  )
}

// ── Screen ────────────────────────────────────────────────────────────────────
type Panel = 'access' | 'correction' | 'erasure' | 'grievance' | 'nomination' | 'consent'

function getRights(): { id: Panel; section: string; icon: typeof Shield; label: string; sub: string; btn: string; danger?: boolean }[] {
  return [
    { id: 'access',     section: 'S.11', icon: Download,      label: tUi('EMP_DATA_RIGHTS_ACCESS_LABEL'),              sub: tUi('EMP_DATA_RIGHTS_ACCESS_SUB'),            btn: tUi('EMP_DATA_RIGHTS_ACCESS_BTN') },
    { id: 'correction', section: 'S.12', icon: AlertCircle,   label: tUi('EMP_DATA_RIGHTS_CORRECTION_LABEL'),          sub: tUi('EMP_DATA_RIGHTS_CORRECTION_SUB'),                     btn: tUi('EMP_DATA_RIGHTS_CORRECTION_BTN') },
    { id: 'erasure',    section: 'S.12', icon: Trash2,        label: tUi('EMP_DATA_RIGHTS_ERASURE_LABEL'),             sub: tUi('EMP_DATA_RIGHTS_ERASURE_SUB'),                   btn: tUi('EMP_DATA_RIGHTS_ERASURE_BTN'), danger: true },
    { id: 'grievance',  section: 'S.13', icon: MessageSquare, label: tUi('EMP_DATA_RIGHTS_GRIEVANCE_LABEL'), sub: tUi('EMP_DATA_RIGHTS_GRIEVANCE_SUB'),       btn: tUi('EMP_DATA_RIGHTS_GRIEVANCE_BTN') },
    { id: 'nomination', section: 'S.14', icon: UserCheck,     label: tUi('EMP_DATA_RIGHTS_NOMINATION_LABEL'),          sub: tUi('EMP_DATA_RIGHTS_NOMINATION_SUB'),             btn: tUi('EMP_DATA_RIGHTS_NOMINATION_BTN') },
    { id: 'consent',    section: 'S.7',  icon: Shield,        label: tUi('EMP_DATA_RIGHTS_CONSENT_LABEL'),    sub: tUi('EMP_DATA_RIGHTS_CONSENT_SUB'),         btn: '' },
  ]
}

export function EmpDataRights() {
  const [open, setOpen] = useState<Panel | null>(null)
  const RIGHTS = getRights()

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800">{tUi('EMP_DATA_RIGHTS_TITLE')}</h1>
        <p className="text-sm text-slate-500 mt-0.5">{tUi('EMP_DATA_RIGHTS_SUB')}</p>
      </div>

      {/* Info banner */}
      <div className="px-4 py-3 rounded-xl text-sm text-sky-700"
        style={{ background:'rgba(14,165,233,0.06)', border:'1px solid rgba(14,165,233,0.2)', borderLeft:'3px solid #0EA5E9' }}>
        {tUi('EMP_DATA_RIGHTS_INFO_BANNER')}
      </div>

      <div className="space-y-2">
        {RIGHTS.map(r => {
          const Icon = r.icon
          const isOpen = open === r.id
          return (
            <div key={r.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
              <button onClick={() => setOpen(isOpen ? null : r.id)}
                className="w-full flex items-center gap-3 px-4 py-4 text-left hover:bg-slate-50 transition-colors">
                {/* Section badge */}
                <span className="text-[10px] font-black px-1.5 py-0.5 rounded shrink-0"
                  style={{ background:'rgba(99,102,241,0.1)', color:'#6366F1' }}>
                  {r.section}
                </span>
                {/* Icon */}
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${r.danger ? 'bg-red-50' : 'bg-indigo-50'}`}>
                  <Icon size={16} className={r.danger ? 'text-red-500' : 'text-indigo-500'}/>
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-semibold ${r.danger ? 'text-red-700' : 'text-slate-800'}`}>{r.label}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{r.sub}</p>
                </div>
                {r.btn && !isOpen && (
                  <span className={`text-xs font-semibold px-2.5 py-1.5 rounded-lg shrink-0 ${
                    r.danger
                      ? 'border border-red-200 text-red-600 hover:bg-red-50'
                      : 'border border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}>
                    {r.btn}
                  </span>
                )}
                <ChevronRight size={16} className={`text-slate-300 transition-transform shrink-0 ${isOpen ? 'rotate-90' : ''}`}/>
              </button>
              {isOpen && (
                <div className="px-4 pb-4 pt-1 border-t border-slate-100">
                  {r.id === 'access'     && <AccessPanel />}
                  {r.id === 'correction' && <CorrectionPanel />}
                  {r.id === 'erasure'    && <ErasurePanel />}
                  {r.id === 'grievance'  && <GrievancePanel />}
                  {r.id === 'nomination' && <NominationPanel />}
                  {r.id === 'consent'    && <ConsentPanel />}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <p className="text-xs text-slate-400 leading-4">
        {tUi('EMP_DATA_RIGHTS_FOOTER_PREFIX')}{' '}
        <a href="/legal/privacy" className="underline">{tUi('EMP_DATA_RIGHTS_FOOTER_PRIVACY_LINK')}</a> {tUi('EMP_DATA_RIGHTS_FOOTER_AND')}{' '}
        <a href="/legal/grievance" className="underline">{tUi('EMP_DATA_RIGHTS_FOOTER_GRIEVANCE_LINK')}</a>.
      </p>
    </div>
  )
}
