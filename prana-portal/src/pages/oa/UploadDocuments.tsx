import { useState, useRef, useCallback } from 'react'
import { Upload, X, FileText, CheckCircle2, AlertCircle, Loader2, ChevronDown, Lock, Sparkles } from 'lucide-react'
import { api } from '@/lib/api'

// ── Constants ─────────────────────────────────────────────────────────────────

const DOC_TYPES = [
  { group: 'HR Letters', options: [
    { value: 'SALARY_SLIP',        label: 'Salary Slip' },
    { value: 'FORM_16',            label: 'Form 16' },
    { value: 'OFFER_LETTER',       label: 'Offer Letter' },
    { value: 'APPOINTMENT_LETTER', label: 'Appointment Letter' },
    { value: 'JOINING_LETTER',     label: 'Joining Letter' },
    { value: 'INCREMENT_LETTER',   label: 'Increment Letter' },
    { value: 'PROMOTION_LETTER',   label: 'Promotion Letter' },
    { value: 'RELIEVING_LETTER',   label: 'Relieving Letter' },
    { value: 'EXPERIENCE_LETTER',  label: 'Experience Letter' },
  ]},
  { group: 'PF & Statutory', options: [
    { value: 'PF_ACKNOWLEDGEMENT', label: 'PF Acknowledgement' },
    { value: 'UAN_ACTIVATION',     label: 'UAN Activation Letter' },
    { value: 'PF_TRANSFER_FORM',   label: 'PF Transfer Form' },
    { value: 'GRATUITY_LETTER',    label: 'Gratuity Letter' },
  ]},
]

const PIPELINE_STAGES = ['QUEUED','ENCRYPTING','SCANNING','EXTRACTING','RESOLVING','ROUTED'] as const
type PipelineStage = typeof PIPELINE_STAGES[number] | 'EXCEPTION' | 'QUARANTINED' | 'ERROR'

const STAGE_LABEL: Record<string, string> = {
  QUEUED: 'Queued', ENCRYPTING: 'Encrypting', SCANNING: 'Scanning',
  EXTRACTING: 'AI Extracting', RESOLVING: 'Resolving', ROUTED: 'Routed',
  EXCEPTION: 'Needs Review', QUARANTINED: 'Quarantined', ERROR: 'Error',
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface FileEntry {
  id: string
  file: File
  status: PipelineStage
  documentId?: string
  error?: string
}

interface UploadSummary {
  total: number
  routed: number
  held: number
  errors: number
}

// ── Sub-components ────────────────────────────────────────────────────────────

function PipelineBar({ stage }: { stage: PipelineStage }) {
  const idx   = PIPELINE_STAGES.indexOf(stage as any)
  const done  = stage === 'ROUTED'
  const error = ['EXCEPTION','QUARANTINED','ERROR'].includes(stage)

  return (
    <div className="mt-2 space-y-1">
      <div className="flex gap-0.5">
        {PIPELINE_STAGES.map((s, i) => (
          <div key={s} className={`h-1 flex-1 rounded-full transition-all duration-500 ${
            done               ? 'bg-emerald-500'
            : error && i <= Math.max(idx, 0) ? 'bg-red-400'
            : i < idx          ? 'bg-violet-500'
            : i === idx && !error ? 'bg-violet-300 animate-pulse'
            : 'bg-slate-200'
          }`} />
        ))}
      </div>
      <div className="flex gap-0.5">
        {PIPELINE_STAGES.map(s => (
          <div key={s} className="flex-1 text-center text-[8px] text-slate-400 leading-none truncate">{STAGE_LABEL[s]}</div>
        ))}
      </div>
    </div>
  )
}

function StageBadge({ stage }: { stage: PipelineStage }) {
  const done  = stage === 'ROUTED'
  const error = ['EXCEPTION','QUARANTINED','ERROR'].includes(stage)
  const cls   = done  ? 'bg-emerald-100 text-emerald-700'
              : error ? 'bg-amber-100 text-amber-700'
              : 'bg-violet-100 text-violet-700'
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-bold rounded-full px-2 py-0.5 ${cls}`}>
      {done  && <CheckCircle2 size={9} />}
      {error && <AlertCircle size={9} />}
      {!done && !error && <Loader2 size={9} className="animate-spin" />}
      {STAGE_LABEL[stage] ?? stage}
    </span>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function UploadDocuments() {
  const [docType,   setDocType]   = useState('')
  const [docPeriod, setDocPeriod] = useState('')
  const [remark,    setRemark]    = useState('')
  const [files,     setFiles]     = useState<FileEntry[]>([])
  const [dragOver,  setDragOver]  = useState(false)
  const [uploading, setUploading] = useState(false)
  const [results,   setResults]   = useState<FileEntry[]>([])
  const [summary,   setSummary]   = useState<UploadSummary | null>(null)
  const esRefs    = useRef<Record<string, EventSource>>({})
  const fileInput = useRef<HTMLInputElement>(null)

  // ── File management ──────────────────────────────────────────────────────

  const addFiles = useCallback((incoming: File[]) => {
    const pdfs = incoming.filter(f => /\.pdf$/i.test(f.name))
    setFiles(prev => {
      const existing = new Set(prev.map(e => e.file.name + e.file.size))
      const novel = pdfs.filter(f => !existing.has(f.name + f.size))
      return [...prev, ...novel.map(f => ({
        id: crypto.randomUUID(), file: f, status: 'QUEUED' as PipelineStage,
      }))]
    })
  }, [])

  const totalBytes = files.reduce((s, e) => s + e.file.size, 0)
  const overLimit  = totalBytes > 500 * 1024 * 1024 || files.length > 2000

  // ── SSE per-file tracking ────────────────────────────────────────────────

  function openSSE(localId: string, documentId: string) {
    const base = (import.meta as any).env?.VITE_API_BASE ?? ''
    const es   = new EventSource(`${base}/api/v1/ingest/status/${documentId}`, { withCredentials: true })
    esRefs.current[localId] = es

    es.onmessage = (e) => {
      const d  = JSON.parse(e.data)
      const st: PipelineStage = d.pipeline_status ?? 'ERROR'
      setResults(prev => {
        const next = prev.map(r => r.id === localId ? { ...r, status: st } : r)
        setSummary({
          total:  next.length,
          routed: next.filter(r => r.status === 'ROUTED').length,
          held:   next.filter(r => ['EXCEPTION','QUARANTINED'].includes(r.status)).length,
          errors: next.filter(r => r.status === 'ERROR').length,
        })
        return next
      })
      if (['ROUTED','EXCEPTION','QUARANTINED'].includes(st)) {
        es.close(); delete esRefs.current[localId]
      }
    }
    es.onerror = () => {
      setResults(prev => prev.map(r =>
        r.id === localId && !['ROUTED','EXCEPTION','QUARANTINED'].includes(r.status)
          ? { ...r, status: 'ERROR', error: 'Status stream disconnected' } : r
      ))
      es.close(); delete esRefs.current[localId]
    }
    setTimeout(() => { es.close(); delete esRefs.current[localId] }, 6 * 60 * 1000)
  }

  // ── Upload ───────────────────────────────────────────────────────────────

  async function handleUpload() {
    if (!docType || !docPeriod || !files.length || overLimit) return
    setUploading(true)
    setSummary(null)

    const form = new FormData()
    files.forEach(e => form.append('files', e.file))
    form.append('doc_type', docType)
    form.append('doc_period', docPeriod)
    if (remark) form.append('comment', remark)

    const initial: FileEntry[] = files.map(e => ({ ...e, status: 'QUEUED' as PipelineStage }))
    setResults(initial)
    setSummary({ total: initial.length, routed: 0, held: 0, errors: 0 })
    setFiles([])

    try {
      const res = await api.post('/v1/ingest/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const apiFiles: Array<{ filename: string; document_id?: string; error?: string }> =
        res.data.files ?? [res.data]

      setResults(prev => prev.map(entry => {
        const match = apiFiles.find(a => a.filename === entry.file.name)
        if (!match) return entry
        if (match.error) return { ...entry, status: 'ERROR', error: match.error }
        if (match.document_id) openSSE(entry.id, match.document_id)
        return { ...entry, documentId: match.document_id, status: 'QUEUED' as PipelineStage }
      }))
    } catch (err: any) {
      const msg = err.response?.data?.detail ?? 'Upload failed'
      setResults(prev => prev.map(e => ({ ...e, status: 'ERROR', error: msg })))
      setSummary(prev => prev ? { ...prev, errors: prev.total } : null)
    } finally {
      setUploading(false)
    }
  }

  const canUpload = !!docType && !!docPeriod && files.length > 0 && !overLimit && !uploading

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">

      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Upload Documents</h1>
        <p className="text-xs text-slate-400 mt-0.5">One document type per batch · PDF only · Max 500 MB</p>
      </div>

      {/* Summary banner — appears after upload */}
      {summary && (
        <div className="flex items-center gap-3 bg-white border border-slate-100 rounded-xl px-5 py-3 shadow-sm">
          <span className="text-sm font-semibold text-slate-700">{summary.total} files submitted</span>
          <span className="text-slate-200">|</span>
          <span className="text-sm text-emerald-600 font-semibold">
            <CheckCircle2 size={13} className="inline mr-1" />{summary.routed} routed to vault
          </span>
          {summary.held > 0 && (
            <><span className="text-slate-200">|</span>
            <span className="text-sm text-amber-600 font-semibold">
              <AlertCircle size={13} className="inline mr-1" />{summary.held} held for review
            </span></>
          )}
          {summary.errors > 0 && (
            <><span className="text-slate-200">|</span>
            <span className="text-sm text-red-500 font-semibold">{summary.errors} errors</span></>
          )}
          {summary.routed + summary.held + summary.errors < summary.total && (
            <span className="ml-auto text-xs text-slate-400 flex items-center gap-1">
              <Loader2 size={11} className="animate-spin" />
              {summary.total - summary.routed - summary.held - summary.errors} processing…
            </span>
          )}
        </div>
      )}

      {/* Two-column layout — matches spec */}
      <div className="grid grid-cols-[1.15fr_1fr] gap-4 items-start">

        {/* ── Left col: New Batch form ── */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-50">
            <span className="font-semibold text-slate-800 text-sm">New Batch</span>
          </div>

          <div className="p-5 flex flex-col gap-4">

            {/* Document Type */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Document Type <span className="text-red-400">*</span>
              </label>
              <div className="relative">
                <select value={docType} onChange={e => setDocType(e.target.value)}
                  className="w-full appearance-none border border-slate-200 rounded-xl px-3 py-2.5 pr-8
                             text-sm focus:outline-none focus:ring-2 focus:ring-violet-400 bg-white text-slate-800">
                  <option value="">— Select type —</option>
                  {DOC_TYPES.map(grp => (
                    <optgroup key={grp.group} label={`─── ${grp.group} ───`}>
                      {grp.options.map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
                <ChevronDown size={13} className="absolute right-3 top-3 text-slate-400 pointer-events-none" />
              </div>
              <p className="text-[10px] text-slate-400">All files in this batch must be the same type. Mixed batches are rejected.</p>
            </div>

            {/* Period / Date */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Period / Date <span className="text-red-400">*</span>
              </label>
              <input value={docPeriod} onChange={e => setDocPeriod(e.target.value)}
                placeholder="e.g. Jun 2024 · FY2023-24 · 2024-06-15"
                className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-violet-400" />
            </div>

            {/* Remark — optional, user-requested addition */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Remark{' '}
                <span className="text-slate-300 font-normal normal-case tracking-normal">(optional)</span>
              </label>
              <input value={remark} onChange={e => setRemark(e.target.value)}
                placeholder="e.g. Q1 FY25 north region salary slips"
                className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-violet-400" />
            </div>

            {/* Drop zone */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Upload Files</label>
              <div
                onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(Array.from(e.dataTransfer.files)) }}
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onClick={() => fileInput.current?.click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                  dragOver ? 'border-violet-400 bg-violet-50' : 'border-slate-200 hover:border-violet-300 hover:bg-slate-50'
                }`}>
                <div className="text-3xl mb-2">📂</div>
                <p className="text-sm font-semibold text-slate-600">Drop PDF files here or click to browse</p>
                <p className="text-[10px] text-slate-400 mt-1">PDF only · Max 500 MB per batch · Up to 2,000 files</p>
                <input ref={fileInput} type="file" accept=".pdf" multiple className="hidden"
                  onChange={e => addFiles(Array.from(e.target.files ?? []))} />
              </div>

              {/* Selected file list */}
              {files.length > 0 && (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-500">
                      {files.length} file{files.length > 1 ? 's' : ''} ·{' '}
                      <span className={overLimit ? 'text-red-500 font-semibold' : 'text-slate-400'}>
                        {(totalBytes / 1024 / 1024).toFixed(1)} MB
                      </span>
                    </span>
                    <button onClick={() => setFiles([])} className="text-red-400 hover:text-red-600">Clear all</button>
                  </div>
                  {overLimit && (
                    <p className="text-xs text-red-500 font-medium">
                      Exceeds 500 MB or 2,000 files limit. Remove files to continue.
                    </p>
                  )}
                  <div className="max-h-44 overflow-y-auto divide-y divide-slate-50 border border-slate-100 rounded-xl">
                    {files.map(e => (
                      <div key={e.id} className="flex items-center gap-2 px-3 py-2 bg-white hover:bg-slate-50">
                        <FileText size={12} className="text-indigo-400 flex-shrink-0" />
                        <span className="flex-1 text-xs text-slate-700 font-mono truncate">{e.file.name}</span>
                        <span className="text-[10px] text-slate-400 flex-shrink-0">{(e.file.size / 1024).toFixed(0)} KB</span>
                        <button onClick={() => setFiles(prev => prev.filter(x => x.id !== e.id))}
                          className="text-slate-300 hover:text-red-500 flex-shrink-0"><X size={12} /></button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* CTA */}
            <button onClick={handleUpload} disabled={!canUpload}
              className="w-full py-2.5 rounded-xl text-sm font-semibold text-white transition-all
                         bg-sky-500 hover:bg-sky-600 disabled:opacity-40 disabled:cursor-not-allowed
                         flex items-center justify-center gap-2">
              {uploading
                ? <><Loader2 size={14} className="animate-spin" />Processing…</>
                : <><Upload size={14} />Start Upload &amp; Process</>}
            </button>
          </div>
        </div>

        {/* ── Right col: What Happens + pipeline results ── */}
        <div className="space-y-4">

          {/* What Happens After Upload — direct from spec */}
          <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-50">
              <span className="font-semibold text-slate-800 text-sm">What Happens After Upload</span>
            </div>
            <div className="p-5 flex flex-col gap-3">
              {[
                { badge: <Sparkles size={11}/>, color: 'text-violet-600 bg-violet-50',
                  text: "Independently classifies every document against declared type. Mismatch → held." },
                { badge: <Sparkles size={11}/>, color: 'text-violet-600 bg-violet-50',
                  text: "Screens against your org's content policy dictionary. Flagged terms → held." },
                { badge: <Sparkles size={11}/>, color: 'text-violet-600 bg-violet-50',
                  text: "Detects cross-employee data contamination. Multiple identities in one doc → blocked." },
                { badge: <Lock size={11}/>, color: 'text-sky-600 bg-sky-50',
                  text: "Encrypted with the employee's personal key. Only they can decrypt." },
                { badge: <Lock size={11}/>, color: 'text-sky-600 bg-sky-50',
                  text: "Once routed to vault, you cannot open or delete it. Ownership transferred." },
              ].map((item, i) => (
                <div key={i} className="flex gap-2.5 items-start">
                  <span className={`flex-shrink-0 w-5 h-5 rounded flex items-center justify-center mt-0.5 ${item.color}`}>
                    {item.badge}
                  </span>
                  <p className="text-xs text-slate-600 leading-relaxed">{item.text}</p>
                </div>
              ))}
              <p className="text-[10px] text-slate-400 border-t border-slate-100 pt-3">
                Held documents go to OA-Admin's Governance Hold queue for review.
              </p>
            </div>
          </div>

          {/* Per-file pipeline status — shown after upload triggered */}
          {results.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
              <div className="px-5 py-3.5 border-b border-slate-50 flex items-center justify-between">
                <span className="font-semibold text-slate-800 text-sm">Pipeline status</span>
                <span className="text-[10px] text-slate-400">Live · auto-updates</span>
              </div>
              <div className="max-h-80 overflow-y-auto divide-y divide-slate-50">
                {results.map(r => (
                  <div key={r.id} className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <FileText size={12} className="text-slate-400 flex-shrink-0" />
                      <span className="flex-1 text-[11px] font-mono text-slate-700 truncate">{r.file.name}</span>
                      <StageBadge stage={r.status} />
                    </div>
                    {r.error
                      ? <p className="text-[10px] text-red-500 mt-1 ml-4">{r.error}</p>
                      : <div className="ml-4"><PipelineBar stage={r.status} /></div>
                    }
                    {r.status === 'EXCEPTION' && (
                      <p className="text-[10px] text-amber-600 mt-1.5 ml-4">
                        Identity unresolved → sent to Governance Hold queue for OA-Admin review
                      </p>
                    )}
                    {r.status === 'ROUTED' && (
                      <p className="text-[10px] text-emerald-600 mt-1.5 ml-4">
                        AI extracted · identity resolved · encrypted & routed ✓
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
