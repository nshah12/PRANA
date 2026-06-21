/**
 * DigestSettings — configure recipients, schedule, and format for the digest.
 * Reads the current user's role from auth store and hits the role-appropriate API.
 * Accessible from CHRO, CFO, and CISO sidebar under "Digest Settings".
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { Plus, X, Mail, Calendar, FileText, CheckCircle } from 'lucide-react'

type Period = 'weekly' | 'monthly' | 'quarterly'

interface DigestConfig {
  recipients: string[]
  schedules: Record<Period, { enabled: boolean; day?: string; day_of_month?: number; time: string } | null>
  sections: string[]
  format: 'email' | 'email_pdf'
  active: boolean
}

const SECTIONS_BY_ROLE: Record<string, { key: string; label: string }[]> = {
  chro: [
    { key: 'vault_health',      label: 'Vault completeness score' },
    { key: 'docs_processed',    label: 'Documents processed' },
    { key: 'exceptions',        label: 'Open exceptions' },
    { key: 'alumni_self_serve', label: 'Alumni self-serve activity' },
    { key: 'dept_breakdown',    label: 'Department completeness breakdown' },
    { key: 'statutory',         label: 'Statutory compliance status' },
  ],
  cfo: [
    { key: 'headcount',         label: 'Headcount vs budget' },
    { key: 'attrition',         label: 'Exits & joiners' },
    { key: 'cost_indicators',   label: 'Cost indicators (estimated)' },
    { key: 'doc_compliance',    label: 'Financial document compliance' },
    { key: 'anomalies',         label: 'Anomaly acknowledgement queue' },
  ],
  ciso: [
    { key: 'access_summary',    label: 'Document access summary' },
    { key: 'anomalies',         label: 'Anomalies & force-logouts' },
    { key: 'by_channel',        label: 'Access by channel breakdown' },
    { key: 'incidents',         label: 'Incident log with severity' },
    { key: 'dpdp',              label: 'DPDP request status' },
  ],
}

const ROLE_LABEL: Record<string, string> = { chro: 'CHRO', cfo: 'CFO', ciso: 'CISO / InfoSec' }
const ROLE_COLOR: Record<string, string> = {
  chro: 'text-indigo-600 bg-indigo-50 border-indigo-200',
  cfo:  'text-cyan-700   bg-cyan-50   border-cyan-200',
  ciso: 'text-emerald-700 bg-emerald-50 border-emerald-200',
}

const DEFAULT_CONFIG: DigestConfig = {
  recipients: [],
  schedules: {
    weekly:    { enabled: false, day: 'MON',   time: '08:00' },
    monthly:   { enabled: false, day_of_month: 1, time: '08:00' },
    quarterly: { enabled: false, time: '08:00' },
  },
  sections: [],
  format: 'email',
  active: false,
}

function endpoint(role: string) {
  const base = role === 'chro' ? 'chro' : role === 'cfo' ? 'cfo' : 'ciso'
  return `/v1/${base}/digest/settings`
}

export function DigestSettings() {
  const user   = useAuthStore(s => s.user)
  const role   = (user?.role ?? 'chro') as string
  const qc     = useQueryClient()
  const qKey   = ['digest-settings', role]

  const { data, isLoading, isError } = useQuery<{ digest_settings: DigestConfig }>({
    queryKey: qKey,
    queryFn:  () => api.get(endpoint(role)).then(r => r.data),
    enabled:  ['chro', 'cfo', 'ciso'].includes(role),
  })

  const [cfg, setCfg] = useState<DigestConfig>(DEFAULT_CONFIG)
  const [newEmail, setNewEmail]   = useState('')
  const [saved, setSaved]         = useState(false)

  useEffect(() => {
    if (data?.digest_settings) setCfg(data.digest_settings)
  }, [data])

  const save = useMutation({
    mutationFn: () => api.put(endpoint(role), cfg),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: qKey })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  function addRecipient() {
    const email = newEmail.trim().toLowerCase()
    if (!email || cfg.recipients.includes(email)) return
    setCfg(c => ({ ...c, recipients: [...c.recipients, email] }))
    setNewEmail('')
  }

  function removeRecipient(email: string) {
    setCfg(c => ({ ...c, recipients: c.recipients.filter(e => e !== email) }))
  }

  function toggleSchedule(period: Period) {
    setCfg(c => ({
      ...c,
      schedules: {
        ...c.schedules,
        [period]: { ...c.schedules[period], enabled: !c.schedules[period]?.enabled },
      },
    }))
  }

  function toggleSection(key: string) {
    setCfg(c => ({
      ...c,
      sections: c.sections.includes(key)
        ? c.sections.filter(s => s !== key)
        : [...c.sections, key],
    }))
  }

  if (!['chro', 'cfo', 'ciso'].includes(role)) {
    return (
      <div className="py-20 text-center text-slate-400 text-sm">
        Digest settings are only available for CHRO, CFO, and CISO roles.
      </div>
    )
  }

  if (isLoading) return (
    <div className="space-y-5 max-w-xl animate-pulse">
      <div className="h-6 w-48 bg-slate-200 rounded"/>
      {[...Array(3)].map((_, i) => <div key={i} className="h-28 bg-slate-100 rounded-xl"/>)}
    </div>
  )

  if (isError) return (
    <div className="py-20 text-center text-slate-400 text-sm">
      Failed to load digest settings.
    </div>
  )

  const colorCls = ROLE_COLOR[role] ?? ROLE_COLOR.chro
  const sections = SECTIONS_BY_ROLE[role] ?? []

  return (
    <div className="space-y-6 max-w-xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Digest Settings</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Configure who receives the {ROLE_LABEL[role]} digest and when.
          </p>
        </div>
        <span className={`text-xs font-medium px-3 py-1 rounded-full border ${colorCls}`}>
          {ROLE_LABEL[role]} digest
        </span>
      </div>

      {/* Recipients */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Mail size={14} className="text-slate-400"/>
          <h2 className="text-sm font-medium text-slate-700">Recipients</h2>
        </div>

        <div className="flex gap-2">
          <input
            type="email"
            placeholder="add recipient email…"
            value={newEmail}
            onChange={e => setNewEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addRecipient()}
            className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2
                       focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <button onClick={addRecipient}
                  className="flex items-center gap-1 text-sm font-medium text-indigo-600
                             border border-indigo-200 px-3 py-2 rounded-lg hover:bg-indigo-50">
            <Plus size={14}/> Add
          </button>
        </div>

        {cfg.recipients.length === 0 ? (
          <p className="text-xs text-slate-400">No recipients configured yet.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {cfg.recipients.map(email => (
              <span key={email}
                    className="inline-flex items-center gap-1.5 text-xs bg-slate-100
                               text-slate-700 px-2.5 py-1 rounded-full">
                {email}
                <button onClick={() => removeRecipient(email)} className="text-slate-400 hover:text-red-500">
                  <X size={11}/>
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Schedule */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Calendar size={14} className="text-slate-400"/>
          <h2 className="text-sm font-medium text-slate-700">Delivery schedule</h2>
        </div>

        {(['weekly', 'monthly', 'quarterly'] as Period[]).map(period => {
          const sched = cfg.schedules[period]
          const enabled = sched?.enabled ?? false
          return (
            <div key={period} className="flex items-start gap-3 py-3 border-b border-slate-50 last:border-0">
              <button
                onClick={() => toggleSchedule(period)}
                className={`mt-0.5 w-9 h-5 rounded-full transition-colors flex-shrink-0 relative
                  ${enabled ? 'bg-indigo-500' : 'bg-slate-200'}`}
              >
                <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all
                  ${enabled ? 'left-4' : 'left-0.5'}`}/>
              </button>
              <div className="flex-1">
                <p className="text-sm font-medium text-slate-700 capitalize">{period}</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {period === 'weekly'    && 'Every Monday 08:00 IST'}
                  {period === 'monthly'   && '1st of each month, 08:00 IST'}
                  {period === 'quarterly' && 'Start of Q1/Q2/Q3/Q4, 08:00 IST'}
                </p>
              </div>
              {enabled && (
                <span className="text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                  Active
                </span>
              )}
            </div>
          )
        })}
      </div>

      {/* Sections */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 space-y-4">
        <div className="flex items-center gap-2">
          <FileText size={14} className="text-slate-400"/>
          <h2 className="text-sm font-medium text-slate-700">Content sections</h2>
          <span className="text-xs text-slate-400 ml-auto">
            {cfg.sections.length === 0 ? 'All sections' : `${cfg.sections.length} selected`}
          </span>
        </div>
        <div className="space-y-2">
          {sections.map(s => (
            <label key={s.key} className="flex items-center gap-3 cursor-pointer py-1.5 group">
              <input
                type="checkbox"
                checked={cfg.sections.length === 0 || cfg.sections.includes(s.key)}
                onChange={() => toggleSection(s.key)}
                className="accent-indigo-600 w-3.5 h-3.5"
              />
              <span className="text-sm text-slate-600 group-hover:text-slate-800">{s.label}</span>
            </label>
          ))}
        </div>
        {cfg.sections.length === 0 && (
          <p className="text-xs text-slate-400">All sections included when none selected.</p>
        )}
      </div>

      {/* Format */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
        <h2 className="text-sm font-medium text-slate-700 mb-3">Delivery format</h2>
        <div className="flex gap-3">
          {(['email', 'email_pdf'] as const).map(fmt => (
            <label key={fmt} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="format" value={fmt}
                     checked={cfg.format === fmt}
                     onChange={() => setCfg(c => ({ ...c, format: fmt }))}
                     className="accent-indigo-600"/>
              <span className="text-sm text-slate-600">
                {fmt === 'email' ? 'Email only' : 'Email + PDF attachment'}
              </span>
            </label>
          ))}
        </div>
      </div>

      {/* Active toggle + Save */}
      <div className="flex items-center justify-between bg-white rounded-xl border border-slate-100 shadow-sm px-5 py-4">
        <label className="flex items-center gap-3 cursor-pointer">
          <button
            onClick={() => setCfg(c => ({ ...c, active: !c.active }))}
            className={`w-10 h-5.5 rounded-full transition-colors relative
              ${cfg.active ? 'bg-indigo-500' : 'bg-slate-200'}`}
            style={{ height: 22, width: 40 }}
          >
            <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all
              ${cfg.active ? 'left-5' : 'left-0.5'}`}/>
          </button>
          <span className="text-sm text-slate-700">
            {cfg.active ? 'Digest active — workflow running' : 'Digest inactive — no emails sent'}
          </span>
        </label>

        <button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="flex items-center gap-2 px-5 py-2 bg-indigo-600 text-white text-sm
                     font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-40"
        >
          {save.isPending ? 'Saving…' : 'Save & activate workflow'}
        </button>
      </div>

      {saved && (
        <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 border border-emerald-200
                        rounded-xl px-4 py-3 text-sm">
          <CheckCircle size={15}/>
          Settings saved. DigestWorkflow will pick up the new schedule on next run.
        </div>
      )}
    </div>
  )
}
