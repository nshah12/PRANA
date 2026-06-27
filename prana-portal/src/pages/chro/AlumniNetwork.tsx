import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, Download, Mail, Phone, MapPin, Calendar, Send } from 'lucide-react'
import { api } from '@/lib/api'

interface AlumniItem {
  employee_uuid:        string
  full_name:            string
  designation:          string
  department:           string
  grade:                string
  city:                 string
  doj:                  string
  dol:                  string
  tenure_band:          string
  time_since_exit:      string
  mobile:               string | null   // null if employee did not share
  email:                string | null   // null if employee did not share
  last_outreach_status: string | null
  last_outreach_at:     string | null
}

interface OutreachSent {
  outreach_id:   string
  employee_uuid: string
  full_name:     string
  designation:   string
  subject:       string
  status:        string
  sent_at:       string
  read_at:       string | null
  replied_at:    string | null
}

const STATUS_BADGE: Record<string, string> = {
  SENT:      'bg-sky-100 text-sky-700',
  READ:      'bg-emerald-100 text-emerald-700',
  REPLIED:   'bg-violet-100 text-violet-700',
  IGNORED:   'bg-slate-100 text-slate-500',
  OPTED_OUT: 'bg-red-100 text-red-600',
}

export function AlumniNetwork() {
  const qc = useQueryClient()
  const [tab, setTab]                   = useState<'browse' | 'messages'>('browse')
  const [filterCity, setFilterCity]     = useState('')
  const [filterDesig, setFilterDesig]   = useState('')
  const [compose, setCompose]           = useState<AlumniItem | null>(null)
  const [subject, setSubject]           = useState('')
  const [bodyText, setBodyText]         = useState('')
  const [composeError, setComposeError] = useState('')
  const [composeDone, setComposeDone]   = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['alumni-list', filterCity, filterDesig],
    queryFn: () => api.get('/v1/alumni/org/list', {
      params: {
        ...(filterCity  ? { city: filterCity }                  : {}),
        ...(filterDesig ? { designation_contains: filterDesig } : {}),
        limit: 200,
      },
    }).then(r => r.data),
  })

  const { data: outreachData } = useQuery({
    queryKey: ['alumni-outreach'],
    queryFn:  () => api.get('/v1/alumni/org/outreach').then(r => r.data),
    enabled:  tab === 'messages',
  })

  const outreachMutation = useMutation({
    mutationFn: (body: { employee_uuid: string; subject: string; body_text: string }) =>
      api.post('/v1/alumni/org/outreach', body).then(r => r.data),
    onSuccess: () => {
      setComposeDone(true)
      qc.invalidateQueries({ queryKey: ['alumni-list'] })
      qc.invalidateQueries({ queryKey: ['alumni-outreach'] })
    },
    onError: (e: any) => setComposeError(e?.response?.data?.detail ?? 'Failed to send'),
  })

  const alumni: AlumniItem[] = data?.items ?? []

  function handleDownload() {
    const params = new URLSearchParams()
    if (filterCity)  params.set('city', filterCity)
    if (filterDesig) params.set('designation_contains', filterDesig)
    window.location.href = `/v1/alumni/org/download?${params.toString()}`
  }

  function openCompose(a: AlumniItem) {
    setCompose(a)
    setSubject('')
    setBodyText('')
    setComposeError('')
    setComposeDone(false)
  }

  function sendOutreach() {
    if (!compose) return
    setComposeError('')
    outreachMutation.mutate({
      employee_uuid: compose.employee_uuid,
      subject,
      body_text: bodyText,
    })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Alumni Network</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Former employees who have opted in to stay connected with your org
          </p>
        </div>
        <button
          onClick={handleDownload}
          className="flex items-center gap-2 px-4 py-2 bg-sky-600 text-white text-sm font-medium rounded-lg hover:bg-sky-700 transition-colors"
        >
          <Download size={15} />
          Download CSV
        </button>
      </div>

      {/* Consent notice */}
      <div className="bg-sky-50 border border-sky-100 rounded-xl px-4 py-3 text-sm text-sky-700">
        Only employees who have explicitly opted in for <strong>your organisation</strong> appear here.
        Contact details (mobile/email) are shown only when the employee chose to share them.
        You may reach out directly via call/email, or send an in-app message.
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-100">
        {(['browse', 'messages'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${
              tab === t
                ? 'border-sky-500 text-sky-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            {t === 'browse' ? `Browse alumni (${alumni.length})` : 'Sent messages'}
          </button>
        ))}
      </div>

      {tab === 'browse' && (
        <>
          {/* Filters */}
          <div className="flex gap-3 flex-wrap">
            {[
              { label: 'City',        value: filterCity,  set: setFilterCity,  ph: 'All cities' },
              { label: 'Designation', value: filterDesig, set: setFilterDesig, ph: 'e.g. Engineer' },
            ].map(f => (
              <div key={f.label}>
                <label className="block text-xs text-slate-500 mb-1">{f.label}</label>
                <input
                  value={f.value}
                  onChange={e => f.set(e.target.value)}
                  placeholder={f.ph}
                  className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500/30 w-44"
                />
              </div>
            ))}
          </div>

          {isLoading && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-56 bg-slate-100 rounded-xl animate-pulse" />
              ))}
            </div>
          )}

          {error && (
            <p className="text-center py-16 text-slate-400">Failed to load alumni</p>
          )}

          {!isLoading && !error && alumni.length === 0 && (
            <div className="text-center py-20 text-slate-400">
              <Users size={40} className="mx-auto mb-3 opacity-30" />
              <p className="font-medium">No consented alumni yet</p>
              <p className="text-sm mt-1 max-w-sm mx-auto">
                Former employees opt in from the PRANA mobile app → Alumni Connect → choose your org.
                They control exactly what contact details to share.
              </p>
            </div>
          )}

          {!isLoading && !error && alumni.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {alumni.map(a => (
                <div key={a.employee_uuid}
                     className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-3">
                  {/* Name + title */}
                  <div>
                    <p className="font-semibold text-slate-800">{a.full_name}</p>
                    <p className="text-sm text-slate-500">
                      {a.designation}{a.department ? ` · ${a.department}` : ''}
                    </p>
                    {a.grade && <p className="text-xs text-slate-400 mt-0.5">{a.grade}</p>}
                  </div>

                  {/* Meta chips */}
                  <div className="flex flex-wrap gap-1.5">
                    {a.city && (
                      <span className="inline-flex items-center gap-1 text-xs bg-slate-50 border border-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
                        <MapPin size={10} /> {a.city}
                      </span>
                    )}
                    <span className="text-xs bg-slate-50 border border-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
                      {a.tenure_band}
                    </span>
                    <span className="text-xs bg-slate-50 border border-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
                      Left {a.time_since_exit}
                    </span>
                  </div>

                  {/* Tenure dates */}
                  <div className="flex items-center gap-1.5 text-xs text-slate-400">
                    <Calendar size={11} />
                    {a.doj} → {a.dol}
                  </div>

                  {/* Contact details — the point of this entire feature */}
                  <div className="space-y-1.5 pt-2 border-t border-slate-50">
                    {a.mobile ? (
                      <a href={`tel:${a.mobile}`}
                         className="flex items-center gap-2 text-sm text-sky-600 hover:underline">
                        <Phone size={13} /> {a.mobile}
                      </a>
                    ) : (
                      <p className="flex items-center gap-2 text-xs text-slate-300">
                        <Phone size={13} /> Not shared by employee
                      </p>
                    )}
                    {a.email ? (
                      <a href={`mailto:${a.email}`}
                         className="flex items-center gap-2 text-sm text-sky-600 hover:underline truncate">
                        <Mail size={13} /> {a.email}
                      </a>
                    ) : (
                      <p className="flex items-center gap-2 text-xs text-slate-300">
                        <Mail size={13} /> Not shared by employee
                      </p>
                    )}
                  </div>

                  {/* Outreach status + in-app message button */}
                  <div className="flex items-center justify-between pt-1">
                    {a.last_outreach_status ? (
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[a.last_outreach_status] ?? ''}`}>
                        {a.last_outreach_status}
                      </span>
                    ) : <span />}
                    <button
                      onClick={() => openCompose(a)}
                      className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-sky-50 text-sky-600 border border-sky-100 rounded-lg hover:bg-sky-100 transition-colors"
                    >
                      <Send size={11} /> In-app message
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Sent messages tab */}
      {tab === 'messages' && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
          {!outreachData?.items?.length ? (
            <p className="text-center py-16 text-slate-400 text-sm">No in-app messages sent yet</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  <th className="text-left px-5 py-3 font-medium text-slate-600">Recipient</th>
                  <th className="text-left px-5 py-3 font-medium text-slate-600">Subject</th>
                  <th className="text-left px-5 py-3 font-medium text-slate-600">Status</th>
                  <th className="text-left px-5 py-3 font-medium text-slate-600">Sent</th>
                </tr>
              </thead>
              <tbody>
                {outreachData.items.map((o: OutreachSent) => (
                  <tr key={o.outreach_id} className="border-b border-slate-50 hover:bg-slate-50/50">
                    <td className="px-5 py-3">
                      <p className="font-medium text-slate-800">{o.full_name}</p>
                      <p className="text-xs text-slate-400">{o.designation}</p>
                    </td>
                    <td className="px-5 py-3 text-slate-600">{o.subject}</td>
                    <td className="px-5 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[o.status] ?? ''}`}>
                        {o.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-slate-400 text-xs">
                      {new Date(o.sent_at).toLocaleDateString('en-IN', {
                        day: 'numeric', month: 'short', year: 'numeric',
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Compose modal */}
      {compose && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
            <div>
              <h2 className="font-semibold text-slate-800 text-lg">Send in-app message</h2>
              <p className="text-sm text-slate-500 mt-0.5">
                To: <span className="font-medium text-slate-700">{compose.full_name}</span>
                {' · '}{compose.designation}
              </p>
            </div>

            <div className="bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 text-xs text-amber-700">
              This message appears in the employee's PRANA app. For faster contact, call or email
              them directly using the details on the card.
            </div>

            {composeDone ? (
              <div className="text-center py-6">
                <p className="text-emerald-600 font-medium">Message sent ✓</p>
                <button onClick={() => setCompose(null)} className="mt-3 text-sm text-slate-500 underline">
                  Close
                </button>
              </div>
            ) : (
              <>
                <div>
                  <label className="text-xs text-slate-500 mb-1 block">Subject</label>
                  <input
                    value={subject}
                    onChange={e => setSubject(e.target.value)}
                    maxLength={200}
                    placeholder="e.g. Exciting opportunity — let's reconnect"
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500/30"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-500 mb-1 block">Message</label>
                  <textarea
                    value={bodyText}
                    onChange={e => setBodyText(e.target.value)}
                    maxLength={2000}
                    rows={5}
                    placeholder="Write a personalised message…"
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500/30 resize-none"
                  />
                  <p className="text-right text-xs text-slate-400 mt-1">{bodyText.length}/2000</p>
                </div>
                {composeError && <p className="text-sm text-red-500">{composeError}</p>}
                <div className="flex gap-2 justify-end">
                  <button onClick={() => setCompose(null)} className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700">
                    Cancel
                  </button>
                  <button
                    onClick={sendOutreach}
                    disabled={!subject.trim() || !bodyText.trim() || outreachMutation.isPending}
                    className="px-4 py-2 text-sm bg-sky-600 text-white rounded-lg hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {outreachMutation.isPending ? 'Sending…' : 'Send'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
