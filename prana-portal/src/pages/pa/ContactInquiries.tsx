import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { fmtDate } from '@/lib/utils'
import { MessageSquare, Building2, Mail, CheckCircle, Clock, XCircle } from 'lucide-react'

type Tab = 'contact' | 'applications'

const STATUS_STYLES: Record<string, { icon: React.ReactNode; cls: string }> = {
  NEW:      { icon: <Clock size={11} />,        cls: 'bg-amber-100 text-amber-700' },
  REVIEWED: { icon: <CheckCircle size={11} />,  cls: 'bg-sky-100 text-sky-700' },
  REPLIED:  { icon: <CheckCircle size={11} />,  cls: 'bg-emerald-100 text-emerald-700' },
  PENDING:  { icon: <Clock size={11} />,        cls: 'bg-amber-100 text-amber-700' },
  APPROVED: { icon: <CheckCircle size={11} />,  cls: 'bg-emerald-100 text-emerald-700' },
  REJECTED: { icon: <XCircle size={11} />,      cls: 'bg-red-100 text-red-700' },
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? { icon: null, cls: 'bg-slate-100 text-slate-500' }
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-bold rounded-full px-2 py-0.5 ${s.cls}`}>
      {s.icon}{status}
    </span>
  )
}

function EnquiryBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    'Organisation onboarding': 'bg-indigo-100 text-indigo-700',
    'Product demo':            'bg-violet-100 text-violet-700',
    'Partnership':             'bg-emerald-100 text-emerald-700',
    'HRMS integration':        'bg-sky-100 text-sky-700',
    'General / Support':       'bg-slate-100 text-slate-600',
  }
  return type ? (
    <span className={`text-[10px] font-semibold rounded-full px-2 py-0.5 ${colors[type] ?? 'bg-slate-100 text-slate-500'}`}>
      {type}
    </span>
  ) : null
}

// ── Contact Messages panel ──────────────────────────────────────────────────
function ContactMessages() {
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['pa-contact-inquiries'],
    queryFn:  () => api.get('/public/contact-inquiries').then(r => r.data),
    refetchInterval: 60_000,
  })
  const items = data?.items ?? []

  return (
    <div className="space-y-3">
      {isLoading && (
        <div className="flex justify-center py-12">
          <div className="w-6 h-6 border-2 border-amber-200 border-t-amber-500 rounded-full animate-spin" />
        </div>
      )}
      {!isLoading && items.length === 0 && (
        <div className="text-center py-12 bg-white rounded-2xl border border-slate-100">
          <MessageSquare size={32} className="mx-auto text-slate-300 mb-2" />
          <p className="text-slate-400 text-sm">No contact messages yet</p>
        </div>
      )}
      {items.map((item: any) => {
        const isOpen = expanded === item.id
        return (
          <div key={item.id}
            className="bg-white rounded-2xl border border-slate-100 overflow-hidden hover:border-slate-200 transition-colors">
            <button className="w-full flex items-center gap-4 px-5 py-4 text-left"
              onClick={() => setExpanded(isOpen ? null : item.id)}>
              <div className="w-9 h-9 rounded-xl bg-indigo-100 flex items-center justify-center
                              text-indigo-600 font-bold text-sm flex-shrink-0">
                {item.name?.charAt(0)?.toUpperCase() ?? '?'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                  <span className="text-sm font-semibold text-slate-800">{item.name}</span>
                  <EnquiryBadge type={item.enquiry_type} />
                  <StatusBadge status={item.status} />
                </div>
                <div className="flex items-center gap-3 text-xs text-slate-400 flex-wrap">
                  <span className="flex items-center gap-1"><Mail size={10}/>{item.email}</span>
                  {item.org && <span className="flex items-center gap-1"><Building2 size={10}/>{item.org}</span>}
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-xs text-slate-400">{fmtDate(item.submitted_at)}</p>
                <p className="text-[10px] text-slate-300 mt-0.5">{isOpen ? '▲' : '▼'}</p>
              </div>
            </button>

            {isOpen && (
              <div className="border-t border-slate-100 px-5 py-4 bg-slate-50 space-y-3">
                {item.message && (
                  <div>
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Message</p>
                    <p className="text-sm text-slate-700 leading-relaxed">{item.message}</p>
                  </div>
                )}
                <div className="flex gap-2 pt-1">
                  <a href={`mailto:${item.email}?subject=Re: ${item.enquiry_type} — PRANA`}
                    className="text-xs font-medium text-indigo-600 border border-indigo-100 bg-white
                               rounded-lg px-3 py-1.5 hover:bg-indigo-50 transition-colors">
                    Reply by email →
                  </a>
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Self-service Applications panel ─────────────────────────────────────────
function Applications() {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({})

  const { data, isLoading } = useQuery({
    queryKey: ['pa-org-applications'],
    queryFn:  () => api.get('/public/org-applications').then(r => r.data),
    refetchInterval: 60_000,
  })
  const items = data?.items ?? []

  const reviewMut = useMutation({
    mutationFn: ({ id, status, notes }: { id: string; status: string; notes: string }) =>
      api.patch(`/public/org-applications/${id}`, { status, review_notes: notes }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-org-applications'] }),
  })

  function handleReview(id: string, status: string) {
    reviewMut.mutate({ id, status, notes: reviewNotes[id] ?? '' })
  }

  return (
    <div className="space-y-3">
      {isLoading && (
        <div className="flex justify-center py-12">
          <div className="w-6 h-6 border-2 border-amber-200 border-t-amber-500 rounded-full animate-spin" />
        </div>
      )}
      {!isLoading && items.length === 0 && (
        <div className="text-center py-12 bg-white rounded-2xl border border-slate-100">
          <Building2 size={32} className="mx-auto text-slate-300 mb-2" />
          <p className="text-slate-400 text-sm">No self-service applications yet</p>
        </div>
      )}
      {items.map((item: any) => {
        const isOpen = expanded === item.id
        return (
          <div key={item.id}
            className="bg-white rounded-2xl border border-slate-100 overflow-hidden hover:border-slate-200 transition-colors">
            <button className="w-full flex items-center gap-4 px-5 py-4 text-left"
              onClick={() => setExpanded(isOpen ? null : item.id)}>
              <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center
                              text-amber-600 font-bold text-sm flex-shrink-0">
                {item.org_name?.slice(0, 2)?.toUpperCase() ?? '??'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                  <span className="text-sm font-semibold text-slate-800">{item.org_name}</span>
                  {item.email_verified && (
                    <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 border border-emerald-100 rounded-full px-2 py-0.5">
                      ✓ Email verified
                    </span>
                  )}
                  <StatusBadge status={item.status} />
                </div>
                <div className="flex items-center gap-3 text-xs text-slate-400 flex-wrap">
                  <span className="font-mono">{item.domain}</span>
                  <span className="flex items-center gap-1"><Mail size={10}/>{item.contact_email}</span>
                  {item.industry && <span>{item.industry}</span>}
                  {item.headcount_band && <span>{item.headcount_band} employees</span>}
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-xs text-slate-400">{fmtDate(item.submitted_at)}</p>
                <p className="text-[10px] text-slate-300 mt-0.5">{isOpen ? '▲' : '▼'}</p>
              </div>
            </button>

            {isOpen && (
              <div className="border-t border-slate-100 px-5 py-4 bg-slate-50 space-y-4">
                {/* All fields */}
                <div className="grid grid-cols-2 gap-x-8 gap-y-2">
                  {[
                    ['Contact name',   item.contact_name],
                    ['Contact email',  item.contact_email],
                    ['Mobile',         item.contact_mobile],
                    ['Entity type',    item.entity_type],
                    ['Industry',       item.industry],
                    ['Headcount band', item.headcount_band],
                    ['How heard',      item.how_heard],
                    ['Agreed to DPA',  item.agreed_to_dpa ? 'Yes' : 'No'],
                  ].map(([k, v]) => v ? (
                    <div key={k as string}>
                      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">{k}</p>
                      <p className="text-sm text-slate-700">{v as string}</p>
                    </div>
                  ) : null)}
                </div>

                {item.message && (
                  <div>
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Message</p>
                    <p className="text-sm text-slate-700 leading-relaxed">{item.message}</p>
                  </div>
                )}

                {/* Review actions — only for PENDING */}
                {item.status === 'PENDING' && (
                  <div className="border-t border-slate-200 pt-4">
                    <p className="text-xs font-semibold text-slate-500 mb-2">Review notes (optional)</p>
                    <textarea
                      className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm resize-none h-20
                                 focus:outline-none focus:ring-2 focus:ring-amber-300 bg-white mb-3"
                      placeholder="Add internal notes…"
                      value={reviewNotes[item.id] ?? ''}
                      onChange={e => setReviewNotes(n => ({ ...n, [item.id]: e.target.value }))}
                    />
                    <div className="flex gap-2">
                      <button onClick={() => window.open(`/admin/tenants/new`, '_blank')}
                        className="flex-1 text-xs font-semibold text-white bg-amber-500 hover:bg-amber-600
                                   rounded-xl py-2.5 transition-colors">
                        Create tenant from this →
                      </button>
                      <button onClick={() => handleReview(item.id, 'REVIEWED')}
                        className="text-xs font-semibold text-sky-700 border border-sky-200 bg-sky-50
                                   hover:bg-sky-100 rounded-xl px-4 py-2.5 transition-colors">
                        Mark reviewed
                      </button>
                      <button onClick={() => handleReview(item.id, 'REJECTED')}
                        className="text-xs font-semibold text-red-600 border border-red-200 bg-red-50
                                   hover:bg-red-100 rounded-xl px-4 py-2.5 transition-colors">
                        Reject
                      </button>
                    </div>
                  </div>
                )}

                {item.status !== 'PENDING' && item.review_notes && (
                  <div>
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Review notes</p>
                    <p className="text-sm text-slate-600">{item.review_notes}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Page shell ───────────────────────────────────────────────────────────────
export function ContactInquiries() {
  const [tab, setTab] = useState<Tab>('contact')

  const contactQuery = useQuery({
    queryKey: ['pa-contact-inquiries'],
    queryFn:  () => api.get('/public/contact-inquiries').then(r => r.data),
  })
  const appQuery = useQuery({
    queryKey: ['pa-org-applications'],
    queryFn:  () => api.get('/public/org-applications').then(r => r.data),
  })

  const contactNew = (contactQuery.data?.items ?? []).filter((i: any) => i.status === 'NEW').length
  const appPending = (appQuery.data?.items ?? []).filter((i: any) => i.status === 'PENDING').length

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Inquiries &amp; Registrations</h1>
        <span className="text-xs text-slate-400 bg-slate-100 rounded-lg px-3 py-1">Auto-refreshes every 60s</span>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 rounded-xl p-1 w-fit">
        <button onClick={() => setTab('contact')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === 'contact' ? 'bg-white shadow text-slate-800' : 'text-slate-500 hover:text-slate-700'
          }`}>
          <MessageSquare size={13}/>
          Contact messages
          {contactNew > 0 && (
            <span className="bg-amber-500 text-white text-[10px] font-bold rounded-full px-1.5 py-0.5">{contactNew}</span>
          )}
        </button>
        <button onClick={() => setTab('applications')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === 'applications' ? 'bg-white shadow text-slate-800' : 'text-slate-500 hover:text-slate-700'
          }`}>
          <Building2 size={13}/>
          Self-service registrations
          {appPending > 0 && (
            <span className="bg-amber-500 text-white text-[10px] font-bold rounded-full px-1.5 py-0.5">{appPending}</span>
          )}
        </button>
      </div>

      {tab === 'contact'      && <ContactMessages />}
      {tab === 'applications' && <Applications />}
    </div>
  )
}
