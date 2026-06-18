import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ShieldAlert, Clock, CheckCircle2, XCircle, AlertTriangle, Timer } from 'lucide-react'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/auth'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ElevationRequest {
  elevation_id:   string
  requestor_name: string
  requestor_id:   string
  duration_hours: 2 | 4 | 8
  reason:         string
  status:         'PENDING' | 'APPROVED' | 'DENIED' | 'EXPIRED' | 'ENDED_EARLY'
  requested_at:   string
  decided_at?:    string
  decided_by_name?: string
  ends_at?:       string
}

interface ActiveElevation {
  elevation_id: string
  ends_at:      string
  duration_hours: number
  reason:       string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

function statusBadge(s: string) {
  const map: Record<string, string> = {
    APPROVED:   'bg-emerald-100 text-emerald-700',
    DENIED:     'bg-red-100 text-red-600',
    EXPIRED:    'bg-slate-100 text-slate-500',
    ENDED_EARLY:'bg-slate-100 text-slate-500',
    PENDING:    'bg-amber-100 text-amber-700',
  }
  const label: Record<string, string> = {
    APPROVED: 'Approved', DENIED: 'Denied', EXPIRED: 'Expired',
    ENDED_EARLY: 'Ended early', PENDING: 'Pending',
  }
  return (
    <span className={`text-[10px] font-bold rounded-full px-2.5 py-0.5 ${map[s] ?? 'bg-slate-100 text-slate-500'}`}>
      {label[s] ?? s}
    </span>
  )
}

// ── OA-Operator view ──────────────────────────────────────────────────────────

function OperatorView({ active }: { active: ActiveElevation | null }) {
  const qc = useQueryClient()
  const [duration, setDuration] = useState<2 | 4 | 8>(2)
  const [reason, setReason]     = useState('')
  const [submitted, setSubmitted] = useState(false)

  const { data: history = [] } = useQuery<ElevationRequest[]>({
    queryKey: ['elevation-history'],
    queryFn: () => api.get('/org/elevations/history').then(r => r.data),
  })

  const { data: adminName } = useQuery<string>({
    queryKey: ['oa-admin-name'],
    queryFn: () => api.get('/org/admin-name').then(r => r.data.name),
    staleTime: 60_000,
  })

  const requestMutation = useMutation({
    mutationFn: () => api.post('/org/elevations', { duration_hours: duration, reason }),
    onSuccess: () => {
      setSubmitted(true)
      setReason('')
      qc.invalidateQueries({ queryKey: ['elevation-history'] })
    },
  })

  const endEarlyMutation = useMutation({
    mutationFn: (id: string) => api.post(`/org/elevations/${id}/end-early`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevation-active'] })
      qc.invalidateQueries({ queryKey: ['elevation-history'] })
    },
  })

  return (
    <div className="space-y-5 max-w-2xl">

      {/* Active window indicator */}
      {active && (
        <div className="bg-amber-50 border border-amber-200 border-l-4 border-l-amber-500 rounded-2xl
                        px-5 py-4 flex items-center gap-4">
          <Timer size={18} className="text-amber-600 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-amber-800">Elevated session is active</p>
            <p className="text-xs text-amber-600 mt-0.5">
              Every document you open during this window is tagged <code className="bg-amber-100 px-1 rounded text-[10px]">ELEVATED</code> in the permanent audit log.
            </p>
          </div>
          <button onClick={() => endEarlyMutation.mutate(active.elevation_id)}
            className="flex-shrink-0 text-xs font-semibold text-amber-700 border border-amber-300
                       px-3 py-1.5 rounded-xl hover:bg-amber-100 transition-colors">
            End early
          </button>
        </div>
      )}

      {/* What elevation means */}
      <div className="bg-amber-50/60 border border-amber-200/60 rounded-2xl px-5 py-4
                      text-sm text-slate-600 leading-relaxed">
        <strong className="text-amber-700">What elevation means:</strong>{' '}
        You will be able to open and view employee documents for the approved duration.
        Every document you open will be tagged{' '}
        <code className="text-[11px] bg-slate-100 px-1.5 py-0.5 rounded font-mono">ELEVATED</code>{' '}
        in the immutable audit log — visible to OA-Admin and Portal Admin permanently.
        Access auto-expires at the end of the window.
      </div>

      {/* New request card */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-50">
          <span className="font-semibold text-slate-800 text-sm">New Elevation Request</span>
        </div>
        <div className="p-5 space-y-4">
          {submitted ? (
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-4
                            flex items-center gap-3">
              <CheckCircle2 size={18} className="text-emerald-600 flex-shrink-0" />
              <div>
                <p className="text-sm font-semibold text-emerald-800">Request sent</p>
                <p className="text-xs text-emerald-600 mt-0.5">
                  {adminName ?? 'Your OA-Admin'} has been notified and will approve or deny your request.
                </p>
              </div>
              <button onClick={() => setSubmitted(false)}
                className="ml-auto text-xs text-emerald-700 underline hover:no-underline">
                New request
              </button>
            </div>
          ) : (
            <>
              {/* Duration */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Access Duration <span className="text-red-400">*</span>
                </label>
                <div className="flex gap-2">
                  {([2, 4, 8] as const).map(h => (
                    <button key={h} onClick={() => setDuration(h)}
                      className={`px-6 py-2 rounded-xl text-sm font-semibold border transition-all ${
                        duration === h
                          ? 'bg-violet-600 border-violet-600 text-white shadow-sm'
                          : 'border-slate-200 text-slate-600 hover:border-violet-300 hover:text-violet-700'
                      }`}>
                      {h} hours
                    </button>
                  ))}
                </div>
              </div>

              {/* Reason */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Reason for Access <span className="text-red-400">*</span>
                </label>
                <textarea value={reason} onChange={e => setReason(e.target.value)} rows={3}
                  placeholder="Describe specifically why you need document access — recorded permanently in the audit log."
                  className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm resize-none
                             focus:outline-none focus:ring-2 focus:ring-violet-400" />
              </div>

              <p className="text-[11px] text-slate-400">
                {adminName ? `${adminName} will be notified immediately.` : 'Your OA-Admin will be notified immediately.'}
                {' '}You cannot self-approve.
              </p>

              <button onClick={() => requestMutation.mutate()}
                disabled={!reason.trim() || requestMutation.isPending || !!active}
                className="w-full py-2.5 rounded-xl text-sm font-semibold text-white transition-all
                           bg-violet-600 hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed">
                {requestMutation.isPending ? 'Sending…'
                  : active ? 'Already in an elevated session'
                  : `Send Request to OA-Admin`}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Past requests */}
      {history.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-50">
            <span className="font-semibold text-slate-800 text-sm">Past Requests</span>
          </div>
          <div className="divide-y divide-slate-50">
            {history.map(r => (
              <div key={r.elevation_id} className="px-5 py-3.5 flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-700">
                    {r.duration_hours}hr — {r.reason.length > 60 ? r.reason.slice(0, 60) + '…' : r.reason}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {fmtDate(r.requested_at)}
                    {r.decided_by_name && ` · ${r.status === 'APPROVED' ? 'Approved' : 'Denied'} by ${r.decided_by_name}`}
                  </p>
                </div>
                {statusBadge(r.status)}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── OA-Admin view ─────────────────────────────────────────────────────────────

function AdminView() {
  const qc = useQueryClient()

  const { data: pending = [] } = useQuery<ElevationRequest[]>({
    queryKey: ['elevation-pending'],
    queryFn:  () => api.get('/org/elevations/pending').then(r => r.data),
    refetchInterval: 15_000,
  })

  const { data: history = [] } = useQuery<ElevationRequest[]>({
    queryKey: ['elevation-history'],
    queryFn:  () => api.get('/org/elevations/history').then(r => r.data),
  })

  const approveMutation = useMutation({
    mutationFn: (id: string) => api.post(`/org/elevations/${id}/approve`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevation-pending'] })
      qc.invalidateQueries({ queryKey: ['elevation-history'] })
    },
  })

  const denyMutation = useMutation({
    mutationFn: (id: string) => api.post(`/org/elevations/${id}/deny`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevation-pending'] })
      qc.invalidateQueries({ queryKey: ['elevation-history'] })
    },
  })

  return (
    <div className="space-y-6 max-w-3xl">

      {/* Pending */}
      <div>
        <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-3">
          Pending Approval
          {pending.length > 0 && (
            <span className="ml-2 bg-amber-100 text-amber-700 rounded-full px-2 py-0.5 normal-case">
              {pending.length}
            </span>
          )}
        </p>

        {pending.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-100 shadow-sm px-5 py-10
                          text-center text-sm text-slate-400">
            No pending elevation requests
          </div>
        ) : (
          <div className="space-y-3">
            {pending.map(req => (
              <div key={req.elevation_id}
                className="bg-white rounded-2xl border border-slate-100 border-l-4 border-l-violet-500 shadow-sm">
                <div className="p-5 flex items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-semibold text-slate-800">{req.requestor_name}</span>
                      <span className="text-[10px] bg-violet-100 text-violet-700 font-bold rounded-full px-2 py-0.5">
                        OA-Operator
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mb-2 flex items-center gap-1.5">
                      <Clock size={11}/>
                      Requested <strong>{req.duration_hours}-hour window</strong> · {fmtDate(req.requested_at)}
                    </p>
                    <div className="bg-slate-50 border-l-2 border-slate-200 rounded-r-xl px-3 py-2
                                    text-xs text-slate-600 italic">
                      "{req.reason}"
                    </div>
                  </div>
                  <div className="flex flex-col gap-2 flex-shrink-0">
                    <button onClick={() => approveMutation.mutate(req.elevation_id)}
                      disabled={approveMutation.isPending}
                      className="flex items-center justify-center gap-1.5 text-xs font-semibold
                                 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-xl
                                 transition-colors min-w-[130px] disabled:opacity-40">
                      <CheckCircle2 size={13}/> Approve {req.duration_hours}hr
                    </button>
                    <button onClick={() => denyMutation.mutate(req.elevation_id)}
                      disabled={denyMutation.isPending}
                      className="flex items-center justify-center gap-1.5 text-xs font-semibold
                                 bg-red-50 hover:bg-red-100 text-red-600 border border-red-200
                                 px-4 py-2 rounded-xl transition-colors disabled:opacity-40">
                      <XCircle size={13}/> Deny
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* History table */}
      <div>
        <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-3">Recent History</p>
        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
          {history.length === 0 ? (
            <p className="px-5 py-8 text-sm text-slate-400 text-center">No elevation history yet</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  {['Requestor', 'Duration', 'Reason', 'Decision', 'When'].map(h => (
                    <th key={h} className="px-4 py-3 text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {history.map(r => (
                  <tr key={r.elevation_id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-4 py-3">
                      <span className="font-semibold text-slate-800 text-xs">{r.requestor_name}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">{r.duration_hours}hr</td>
                    <td className="px-4 py-3 text-xs text-slate-500 max-w-[200px] truncate">{r.reason}</td>
                    <td className="px-4 py-3">{statusBadge(r.status)}</td>
                    <td className="px-4 py-3 text-xs text-slate-400">{fmtDate(r.decided_at ?? r.requested_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/50">
            <p className="text-[10px] text-slate-400 text-center">
              All elevation decisions are permanently recorded in the audit log regardless of outcome.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Page shell ────────────────────────────────────────────────────────────────

export function ElevationPage() {
  const { user } = useAuthStore()
  const isAdmin  = user?.role === 'oa_admin'

  const { data: active } = useQuery<ActiveElevation | null>({
    queryKey: ['elevation-active'],
    queryFn:  () => api.get('/org/elevations/active').then(r => r.data).catch(() => null),
    refetchInterval: 60_000,
    enabled: !isAdmin,
  })

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">
          {isAdmin ? 'Elevation Approvals' : 'Request Elevation'}
        </h1>
        <p className="text-xs text-slate-400 mt-0.5">
          {isAdmin
            ? 'Temporary document access requests from OA-Operators'
            : 'Temporary document access — requires OA-Admin approval'}
        </p>
      </div>

      {isAdmin ? <AdminView /> : <OperatorView active={active ?? null} />}
    </div>
  )
}
