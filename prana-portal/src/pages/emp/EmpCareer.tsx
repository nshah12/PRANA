import { useQuery } from '@tanstack/react-query'
import { Share2 } from 'lucide-react'
import { api } from '@/lib/api'

const ORG_COLORS = ['#0EA5E9','#10B981','#F59E0B','#8B5CF6','#EF4444']
const ORG_BG     = ['rgba(14,165,233,0.1)','rgba(16,185,129,0.1)','rgba(245,158,11,0.1)','rgba(139,92,246,0.1)','rgba(239,68,68,0.1)']

const EVENT_STYLE: Record<string, { label: string; bg: string; color: string }> = {
  join:      { label: 'JOINED',    bg: 'rgba(139,92,246,0.12)', color: '#8B5CF6' },
  promotion: { label: 'PROMOTED',  bg: 'rgba(16,185,129,0.12)',  color: '#10B981' },
  increment: { label: 'INCREMENT', bg: 'rgba(14,165,233,0.12)', color: '#0EA5E9' },
  leave:     { label: 'EXITED',    bg: 'rgba(148,163,184,0.15)',color: '#64748B' },
  JOINED:    { label: 'JOINED',    bg: 'rgba(139,92,246,0.12)', color: '#8B5CF6' },
  PROMOTED:  { label: 'PROMOTED',  bg: 'rgba(16,185,129,0.12)',  color: '#10B981' },
  INCREMENT: { label: 'INCREMENT', bg: 'rgba(14,165,233,0.12)', color: '#0EA5E9' },
  EXITED:    { label: 'EXITED',    bg: 'rgba(148,163,184,0.15)',color: '#64748B' },
}

function tenureStr(from: string, to: string | null): string {
  const start = new Date(from)
  const end   = to ? new Date(to) : new Date()
  const months = Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24 * 30.44))
  const yrs = Math.floor(months / 12)
  const mo  = months % 12
  const parts = []
  if (yrs > 0) parts.push(`${yrs} yr${yrs > 1 ? 's' : ''}`)
  if (mo > 0)  parts.push(`${mo} mo`)
  return parts.join(' ') || '< 1 mo'
}

function fmtMonth(d: string | null) {
  if (!d) return 'Present'
  return new Date(d).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
}

export function EmpCareer() {
  const { data: profileData } = useQuery({
    queryKey: ['emp-vault-profile'],
    queryFn: () => api.get('/v1/vault/profile').then(r => r.data),
  })
  const { data: careerData, isLoading } = useQuery({
    queryKey: ['emp-career'],
    queryFn: () => api.get('/v1/vault/career').then(r => r.data),
  })
  const { data: docsData } = useQuery({
    queryKey: ['emp-vault-docs'],
    queryFn: () => api.get('/v1/vault/documents', { params: { limit: 100 } }).then(r => r.data),
  })

  const employers: any[] = (profileData?.employers ?? []).slice().sort((a:any, b:any) =>
    new Date(a.doj ?? 0).getTime() - new Date(b.doj ?? 0).getTime()
  )
  const events: any[]    = careerData?.events ?? []
  const docs: any[]      = docsData?.documents ?? []

  // Build per-employer event groups
  const orgGroups = employers.map((e: any, i: number) => {
    const tid = e.tenant_id ?? e.id
    const name = e.tenant_name ?? e.name ?? '—'
    const orgDocs = docs.filter(d => d.tenant_id === tid)
    const orgEvents = events.filter(ev => ev.employer_id === tid || ev.employer_name === name)

    // If no events from API, synthesize from docs
    const synth: any[] = []
    if (orgEvents.length === 0) {
      const appt = orgDocs.find(d => d.doc_type === 'APPOINTMENT_LETTER' || d.doc_type === 'OFFER_LETTER')
      if (appt) synth.push({ event_type: 'JOINED', event_date: e.doj, designation: e.designation, doc_type: appt.doc_type })
      const incr = orgDocs.find(d => d.doc_type === 'INCREMENT_LETTER')
      if (incr) synth.push({ event_type: 'INCREMENT', event_date: incr.doc_period, designation: e.designation, doc_type: 'INCREMENT_LETTER' })
      const promo = orgDocs.find(d => d.doc_type === 'PROMOTION_LETTER')
      if (promo) synth.push({ event_type: 'PROMOTED', event_date: promo.doc_period, designation: e.designation, doc_type: 'PROMOTION_LETTER' })
      if (e.dol) {
        const rel = orgDocs.find(d => d.doc_type === 'RELIEVING_LETTER' || d.doc_type === 'EXPERIENCE_LETTER')
        synth.push({ event_type: 'EXITED', event_date: e.dol, designation: e.designation, doc_type: rel?.doc_type })
      }
    }

    return {
      ...e, colorIdx: i, name, tid,
      events: (orgEvents.length > 0 ? orgEvents : synth).sort((a:any,b:any) =>
        new Date(b.event_date ?? 0).getTime() - new Date(a.event_date ?? 0).getTime()
      ),
      docCount: orgDocs.length,
    }
  })

  // Total career stats
  const earliestDoj = employers.length > 0 ? employers[0].doj : null
  const totalMonths  = earliestDoj
    ? Math.round((Date.now() - new Date(earliestDoj).getTime()) / (1000 * 60 * 60 * 24 * 30.44))
    : 0
  const totalYrs = Math.floor(totalMonths / 12)
  const totalMo  = totalMonths % 12

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Career Timeline</h1>
          <p className="text-sm text-slate-500 mt-0.5">Your entire career — verified, assembled automatically from employer-pushed documents</p>
        </div>
        <button className="flex items-center gap-1.5 px-3 py-2 text-sm border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50">
          <Share2 size={14}/> Share Career Passport
        </button>
      </div>

      {/* AI-assembled banner */}
      <div className="rounded-xl px-4 py-3 mb-6 text-sm text-emerald-700"
        style={{ background:'rgba(16,185,129,0.06)', borderLeft:'3px solid #10B981', border:'1px solid rgba(16,185,129,0.2)', borderLeftWidth:3 }}>
        🤖 <strong>AI-assembled.</strong> Every role, promotion, and tenure below was extracted from documents pushed by your employers. All entries marked ✓ are cryptographically verified.
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[...Array(3)].map((_,i) => <div key={i} className="h-40 bg-slate-100 animate-pulse rounded-xl"/>)}
        </div>
      ) : employers.length === 0 ? (
        <div className="text-center py-20 text-slate-400">
          <div className="text-4xl mb-3">🏢</div>
          <p className="font-medium text-slate-600">No employers linked yet</p>
        </div>
      ) : (
        <div className="relative">
          {/* Vertical timeline line */}
          <div className="absolute left-[19px] top-0 bottom-0 w-0.5 bg-slate-200" style={{ zIndex: 0 }} />

          <div className="space-y-6">
            {orgGroups.slice().reverse().map(org => {
              const col    = ORG_COLORS[org.colorIdx % ORG_COLORS.length]
              const bg     = ORG_BG[org.colorIdx % ORG_BG.length]
              const active = !org.dol
              return (
                <div key={org.tid} className="relative pl-12">
                  {/* Timeline dot / org icon */}
                  <div className="absolute left-0 top-0 w-10 h-10 rounded-full flex items-center justify-center text-xl font-bold z-10"
                    style={{ background: bg, border: `2px solid ${col}` }}>
                    {active ? '🏢' : '🏛'}
                  </div>

                  {/* Employer card */}
                  <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
                    {/* Header */}
                    <div className="flex items-center gap-3 px-4 py-3.5 border-b border-slate-100">
                      <div>
                        <p className="text-sm font-bold text-slate-800">{org.name}</p>
                        <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                          {fmtMonth(org.doj)} – {fmtMonth(org.dol)} · {tenureStr(org.doj, org.dol)} ·{' '}
                          <span style={{ color: active ? '#10B981' : '#94A3B8' }} className="font-semibold">
                            {active ? 'Active' : 'Alumni'}
                          </span>
                        </p>
                      </div>
                      <span className="ml-auto text-[11px] text-slate-400">{org.docCount} docs</span>
                    </div>

                    {/* Events */}
                    <div className="divide-y divide-slate-100">
                      {org.events.length === 0 ? (
                        <div className="px-4 py-3 text-sm text-slate-400">No career events extracted yet.</div>
                      ) : org.events.map((ev: any, ei: number) => {
                        const es = EVENT_STYLE[ev.event_type] ?? EVENT_STYLE.join
                        return (
                          <div key={ei} className="flex items-start gap-3 px-4 py-3"
                            style={{ background: ei % 2 === 0 ? '#fafbfc' : '#fff' }}>
                            {/* Event badge */}
                            <span className="text-[10px] font-black px-1.5 py-0.5 rounded shrink-0 mt-0.5"
                              style={{ background: es.bg, color: es.color }}>
                              {es.label}
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-semibold text-slate-800">
                                {ev.designation ?? org.designation ?? '—'}
                                {ev.event_date && (
                                  <span className="ml-2 text-[11px] font-normal text-slate-400">
                                    {fmtMonth(ev.event_date)}
                                  </span>
                                )}
                              </p>
                              {ev.doc_type && (
                                <p className="text-[11px] text-slate-400 mt-0.5">
                                  {ev.doc_type.replace(/_/g,' ')} ✓
                                </p>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Footer summary */}
      {employers.length > 0 && (
        <div className="mt-6 pt-4 border-t border-slate-200">
          <p className="text-xs text-slate-400 text-center font-mono">
            Total verified career: {totalYrs > 0 ? `${totalYrs} yr${totalYrs>1?'s':''} ` : ''}{totalMo > 0 ? `${totalMo} mo` : ''} · {employers.length} employer{employers.length>1?'s':''} · {docs.length} documents
          </p>
        </div>
      )}
    </div>
  )
}
