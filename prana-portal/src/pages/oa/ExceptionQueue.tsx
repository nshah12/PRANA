import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Search, CheckCircle2, X, Clock, ChevronRight, UserSearch } from 'lucide-react'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/auth'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Candidate {
  employee_uuid: string
  name: string
  emp_id: string
  confidence: number
}

interface ExceptionItem {
  exception_id: string
  document_id: string
  doc_type: string
  doc_period: string | null
  exception_type: 'MULTIPLE_CANDIDATES' | 'NO_MATCH' | 'LOW_CONFIDENCE' | 'PIPELINE_TIMEOUT'
  extracted_fields: Record<string, string>
  candidate_matches: Candidate[]
  status: string
  raised_at: string
  sla_hours?: number      // hours since raised — computed server-side ideally, or derived
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const DOC_TYPE_LABEL: Record<string, string> = {
  SALARY_SLIP: 'Salary Slip', FORM_16: 'Form 16', OFFER_LETTER: 'Offer Letter',
  APPOINTMENT_LETTER: 'Appointment Letter', JOINING_LETTER: 'Joining Letter',
  INCREMENT_LETTER: 'Increment Letter', PROMOTION_LETTER: 'Promotion Letter',
  RELIEVING_LETTER: 'Relieving Letter', EXPERIENCE_LETTER: 'Experience Letter',
  PF_ACKNOWLEDGEMENT: 'PF Acknowledgement', UAN_ACTIVATION: 'UAN Activation Letter',
  PF_TRANSFER_FORM: 'PF Transfer Form', GRATUITY_LETTER: 'Gratuity Letter',
}

const EX_TYPE_LABEL: Record<string, string> = {
  MULTIPLE_CANDIDATES: 'Multiple candidates',
  NO_MATCH:            'No match found',
  LOW_CONFIDENCE:      'Low confidence',
  PIPELINE_TIMEOUT:    'Pipeline timeout',
}

function hoursAgo(isoDate: string): number {
  return Math.floor((Date.now() - new Date(isoDate).getTime()) / 3_600_000)
}

function confidenceColor(c: number) {
  if (c >= 0.85) return 'text-emerald-600'
  if (c >= 0.70) return 'text-amber-500'
  return 'text-red-500'
}

// ── Exception card ────────────────────────────────────────────────────────────

function ExceptionCard({
  item, isAdmin, onAssign, onDismiss,
}: {
  item: ExceptionItem
  isAdmin: boolean
  onAssign: (exId: string, empUuid: string, empName: string) => void
  onDismiss: (exId: string) => void
}) {
  const [searchMode, setSearchMode] = useState(false)
  const [searchQ, setSearchQ]       = useState('')
  const [searchResults, setSearchResults] = useState<Candidate[]>([])
  const [searching, setSearching]   = useState(false)

  const hrs           = hoursAgo(item.raised_at)
  const slaBreach     = hrs >= 24
  const slaWarning    = hrs >= 4 && !slaBreach
  const borderColor   = slaBreach ? 'border-l-red-500' : slaWarning ? 'border-l-amber-400' : 'border-l-slate-200'

  async function runSearch() {
    if (!searchQ.trim()) return
    setSearching(true)
    try {
      const res = await api.get('/v1/org/employees/search', { params: { q: searchQ } })
      setSearchResults(res.data)
    } finally {
      setSearching(false)
    }
  }

  const displayName = item.extracted_fields?.name ?? item.extracted_fields?.employee_name ?? 'Unknown'

  return (
    <div className={`bg-white rounded-2xl border border-slate-100 border-l-4 ${borderColor} shadow-sm overflow-hidden`}>
      {/* Card header */}
      <div className="px-5 py-4 border-b border-slate-50 flex items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {slaBreach && (
            <span className="flex-shrink-0 inline-flex items-center gap-1 text-[10px] font-bold
                             bg-red-100 text-red-600 rounded-full px-2.5 py-1">
              <AlertTriangle size={9}/> SLA BREACH — {hrs}hr
            </span>
          )}
          {slaWarning && (
            <span className="flex-shrink-0 inline-flex items-center gap-1 text-[10px] font-bold
                             bg-amber-100 text-amber-600 rounded-full px-2.5 py-1">
              <Clock size={9}/> {hrs}hr
            </span>
          )}
          {!slaBreach && !slaWarning && (
            <span className="flex-shrink-0 text-[10px] text-slate-400">{hrs}hr ago</span>
          )}
          <span className="text-sm font-semibold text-slate-800 truncate">
            {DOC_TYPE_LABEL[item.doc_type] ?? item.doc_type}
            {displayName !== 'Unknown' && ` · ${displayName}`}
          </span>
        </div>
        <span className="flex-shrink-0 inline-flex text-[10px] font-bold bg-slate-100 text-slate-600 rounded-full px-2.5 py-1">
          {EX_TYPE_LABEL[item.exception_type] ?? item.exception_type}
        </span>
      </div>

      {/* Card body */}
      <div className="p-5">
        <div className="grid grid-cols-2 gap-5 mb-4">

          {/* Extracted fields */}
          <div>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Extracted fields</p>
            <div className="space-y-1">
              {Object.entries(item.extracted_fields).map(([k, v]) => (
                <div key={k} className="flex gap-1.5 text-xs">
                  <span className="text-slate-400 capitalize flex-shrink-0">
                    {k.replace(/_/g, ' ')}:
                  </span>
                  <span className="text-slate-700 font-medium">
                    {/* PAN always redacted in UI — privacy contract */}
                    {k.toLowerCase().includes('pan') ? '[REDACTED]' : String(v)}
                  </span>
                </div>
              ))}
              {item.doc_period && (
                <div className="flex gap-1.5 text-xs">
                  <span className="text-slate-400">Period:</span>
                  <span className="text-slate-700 font-medium">{item.doc_period}</span>
                </div>
              )}
            </div>
          </div>

          {/* Candidates */}
          <div>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">
              Candidates
              {item.candidate_matches.length === 0 && (
                <span className="ml-1 text-amber-500 normal-case font-normal">— no matches</span>
              )}
            </p>
            {item.candidate_matches.length > 0 ? (
              <div className="space-y-1.5">
                {item.candidate_matches.map(c => (
                  <button
                    key={c.employee_uuid}
                    onClick={() => isAdmin && onAssign(item.exception_id, c.employee_uuid, c.name)}
                    disabled={!isAdmin}
                    className="w-full flex items-center justify-between text-xs px-3 py-2 rounded-xl
                               bg-slate-50 hover:bg-violet-50 hover:border-violet-200 border border-transparent
                               transition-all disabled:cursor-not-allowed disabled:hover:bg-slate-50">
                    <span className="text-slate-700">
                      {c.name}
                      <span className="text-slate-400 ml-1">· {c.emp_id}</span>
                    </span>
                    <span className={`font-bold ${confidenceColor(c.confidence)}`}>
                      {(c.confidence * 100).toFixed(0)}%
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-amber-600">
                No employees matched at any resolution level
              </p>
            )}
          </div>
        </div>

        {/* Search & assign panel */}
        {searchMode && isAdmin && (
          <div className="mb-4 bg-slate-50 rounded-xl p-4 space-y-3">
            <p className="text-xs font-semibold text-slate-600">Search employee master</p>
            <div className="flex gap-2">
              <input
                value={searchQ} onChange={e => setSearchQ(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && runSearch()}
                placeholder="Name, Emp ID, email…"
                className="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-xs
                           focus:outline-none focus:ring-2 focus:ring-violet-400" />
              <button onClick={runSearch}
                className="px-4 py-2 bg-violet-600 text-white text-xs font-semibold rounded-xl
                           hover:bg-violet-700 flex items-center gap-1.5">
                {searching ? '…' : <><Search size={12}/>Search</>}
              </button>
            </div>
            {searchResults.length > 0 && (
              <div className="space-y-1">
                {searchResults.map(r => (
                  <button key={r.employee_uuid}
                    onClick={() => { onAssign(item.exception_id, r.employee_uuid, r.name); setSearchMode(false) }}
                    className="w-full flex items-center justify-between text-xs px-3 py-2.5
                               bg-white rounded-xl border border-slate-200 hover:border-violet-300
                               hover:bg-violet-50 transition-all">
                    <span className="text-slate-700 font-medium">{r.name} · <span className="text-slate-400">{r.emp_id}</span></span>
                    <span className="text-violet-600 font-semibold flex items-center gap-1">
                      Assign <ChevronRight size={12}/>
                    </span>
                  </button>
                ))}
              </div>
            )}
            {searchResults.length === 0 && !searching && searchQ && (
              <p className="text-xs text-slate-400">No results for "{searchQ}"</p>
            )}
          </div>
        )}

        {/* Actions */}
        {isAdmin ? (
          <div className="flex items-center gap-2">
            {item.candidate_matches.length > 0 && (
              <button
                onClick={() => onAssign(item.exception_id, item.candidate_matches[0].employee_uuid, item.candidate_matches[0].name)}
                className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white text-xs font-semibold
                           rounded-xl transition-colors flex items-center gap-1.5">
                <CheckCircle2 size={12}/>
                Assign to {item.candidate_matches[0]?.name?.split(' ')[0]}
              </button>
            )}
            <button
              onClick={() => setSearchMode(m => !m)}
              className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold
                         rounded-xl transition-colors flex items-center gap-1.5">
              <UserSearch size={12}/>
              {searchMode ? 'Cancel search' : 'Search & Assign'}
            </button>
            <button
              onClick={() => onDismiss(item.exception_id)}
              className="ml-auto px-4 py-2 bg-red-50 hover:bg-red-100 text-red-600 text-xs font-semibold
                         rounded-xl transition-colors flex items-center gap-1.5">
              <X size={12}/>
              Dismiss
            </button>
          </div>
        ) : (
          <p className="text-xs text-slate-400 bg-slate-50 rounded-xl px-4 py-2.5">
            Identity resolution requires OA-Admin access. Contact your OA-Admin to assign this document.
          </p>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function ExceptionQueue() {
  const { user }  = useAuthStore()
  const isAdmin   = user?.role === 'oa_admin'
  const qc        = useQueryClient()
  const [filter, setFilter] = useState<string>('ALL')

  const { data: items = [], isLoading } = useQuery<ExceptionItem[]>({
    queryKey: ['exceptions'],
    queryFn: () => api.get('/v1/org/exceptions').then(r => r.data?.exceptions ?? r.data),
    refetchInterval: 30_000,
  })

  const assignMutation = useMutation({
    mutationFn: ({ exId, empUuid }: { exId: string; empUuid: string; empName: string }) =>
      api.post(`/v1/org/exceptions/${exId}/resolve`, { employee_uuid: empUuid }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exceptions'] }),
  })

  const dismissMutation = useMutation({
    mutationFn: (exId: string) => api.post(`/v1/org/exceptions/${exId}/dismiss`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exceptions'] }),
  })

  const breaching = items.filter(i => hoursAgo(i.raised_at) >= 24)
  const _warning  = items.filter(i => { const h = hoursAgo(i.raised_at); return h >= 4 && h < 24 })

  const filtered = filter === 'ALL'       ? items
                 : filter === 'BREACH'    ? breaching
                 : filter === 'NO_MATCH'  ? items.filter(i => i.exception_type === 'NO_MATCH')
                 : items.filter(i => i.exception_type === filter)

  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Exception Queue</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Documents that failed all 4 resolution levels — requires manual assignment
          </p>
        </div>
        <div className="text-xs text-slate-400">
          {items.length} open
          {breaching.length > 0 && (
            <span className="ml-2 text-red-500 font-semibold">· {breaching.length} breaching SLA</span>
          )}
        </div>
      </div>

      {/* SLA breach banner */}
      {breaching.length > 0 && (
        <div className="bg-red-50 border border-red-100 border-l-4 border-l-red-500 rounded-xl px-5 py-3
                        flex items-center gap-3">
          <AlertTriangle size={16} className="text-red-500 flex-shrink-0" />
          <p className="text-sm text-red-700">
            <strong>{breaching.length} document{breaching.length > 1 ? 's' : ''}</strong> have exceeded
            the 24-hour SLA and been escalated to Portal Admin.
            {!isAdmin && ' Contact your OA-Admin to resolve.'}
          </p>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-1.5">
        {[
          { key: 'ALL',               label: `All (${items.length})` },
          { key: 'BREACH',            label: `SLA Breach (${breaching.length})` },
          { key: 'MULTIPLE_CANDIDATES', label: 'Multiple candidates' },
          { key: 'NO_MATCH',          label: 'No match' },
          { key: 'LOW_CONFIDENCE',    label: 'Low confidence' },
        ].map(f => (
          <button key={f.key} onClick={() => setFilter(f.key)}
            className={`text-xs font-medium px-3 py-1.5 rounded-full transition-colors ${
              filter === f.key
                ? 'bg-slate-800 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}>
            {f.label}
          </button>
        ))}
      </div>

      {/* Queue */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20 text-slate-400 text-sm">
          Loading exceptions…
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <CheckCircle2 size={36} className="text-emerald-400 mb-3" />
          <p className="text-sm font-semibold text-slate-700">No open exceptions</p>
          <p className="text-xs text-slate-400 mt-1">All documents resolved — vault is clean</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map(item => (
            <ExceptionCard
              key={item.exception_id}
              item={item}
              isAdmin={isAdmin}
              onAssign={(exId, empUuid, empName) =>
                assignMutation.mutate({ exId, empUuid, empName })
              }
              onDismiss={exId => dismissMutation.mutate(exId)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
