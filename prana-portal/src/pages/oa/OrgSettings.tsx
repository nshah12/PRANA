/**
 * OA Admin — Org Settings
 *
 * Configures how employees receive their activation credentials (temp password + link).
 * Stored in tenant_config as employee_activation_channels (comma-separated list).
 *
 * API: GET  /org/settings → { employee_activation_channels, self_upload_policy, ... }
 *      PATCH /org/settings { employee_activation_channels: "personal_email,sms" }
 */
import { useEffect, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Settings, Save, AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import { api } from '@/lib/api'

type Channel = 'personal_email' | 'work_email' | 'sms'

const CHANNEL_META: Record<Channel, { label: string; desc: string; bfsiAllowed: boolean }> = {
  personal_email: {
    label: 'Personal email',
    desc: 'Temp password sent to the employee\'s personal email address (from employee record).',
    bfsiAllowed: true,
  },
  work_email: {
    label: 'Work / corporate email',
    desc: 'Sent to the employee\'s work email (must match your domain). Reliable for active employees.',
    bfsiAllowed: true,
  },
  sms: {
    label: 'SMS to registered mobile',
    desc: 'Sent as a text message to the mobile number in the employee record.',
    bfsiAllowed: false,
  },
}

function parseChannels(raw: string | undefined): Set<Channel> {
  if (!raw) return new Set(['personal_email'])
  return new Set(raw.split(',').filter(Boolean) as Channel[])
}

export function OrgSettings() {
  const { data, isLoading } = useQuery({
    queryKey: ['org-settings'],
    queryFn: () => api.get('/org/settings').then(r => r.data),
  })

  const [channels, setChannels] = useState<Set<Channel>>(new Set(['personal_email']))
  const [dirty, setDirty]       = useState(false)
  const [saved, setSaved]       = useState(false)

  useEffect(() => {
    if (data?.employee_activation_channels) {
      setChannels(parseChannels(data.employee_activation_channels))
      setDirty(false)
    }
  }, [data])

  const isBfsi = data?.self_upload_policy === 'BLOCKED_ENTIRELY'

  function toggle(ch: Channel) {
    if (isBfsi && !CHANNEL_META[ch].bfsiAllowed) return
    setChannels(prev => {
      const next = new Set(prev)
      if (next.has(ch)) {
        if (next.size === 1) return prev  // must keep at least one
        next.delete(ch)
      } else {
        next.add(ch)
      }
      return next
    })
    setDirty(true)
    setSaved(false)
  }

  const saveMutation = useMutation({
    mutationFn: () => api.patch('/org/settings', {
      employee_activation_channels: [...channels].join(','),
    }),
    onSuccess: () => {
      setDirty(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const activeSmsButBfsi = isBfsi && channels.has('sms')

  return (
    <div className="space-y-6 max-w-xl">
      <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
        <Settings size={18} /> Org Settings
      </h1>

      {isBfsi && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex gap-2">
          <AlertTriangle size={15} className="text-amber-600 mt-0.5 shrink-0" />
          <p className="text-xs text-amber-700">
            <strong>BFSI tenant</strong> — SMS-only activation is not permitted. At least one email channel must be enabled.
            Contact Platform Admin to request a policy exception.
          </p>
        </div>
      )}

      {/* ── Employee Activation Channels ── */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-5">
        <div>
          <h2 className="font-medium text-slate-800">Employee Activation Channels</h2>
          <p className="text-xs text-slate-500 mt-1">
            When a document is pushed for a new employee, PRANA sends their temporary password
            via every channel you enable below. Select one or more.
          </p>
        </div>

        <div className="space-y-3">
          {(Object.keys(CHANNEL_META) as Channel[]).map(ch => {
            const meta    = CHANNEL_META[ch]
            const checked = channels.has(ch)
            const locked  = isBfsi && !meta.bfsiAllowed

            return (
              <label key={ch}
                className={`flex items-start gap-3 p-4 border rounded-xl cursor-pointer transition-colors select-none
                  ${locked ? 'opacity-40 cursor-not-allowed' : 'hover:border-violet-300'}
                  ${checked && !locked ? 'border-violet-500 bg-violet-50' : 'border-slate-200'}`}
                onClick={() => !locked && toggle(ch)}
              >
                {/* Checkbox */}
                <div className={`mt-0.5 w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 transition-colors
                  ${checked && !locked ? 'border-violet-600 bg-violet-600' : 'border-slate-300 bg-white'}`}>
                  {checked && !locked && (
                    <svg viewBox="0 0 10 8" className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path d="M1 4l3 3 5-6" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800">{meta.label}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{meta.desc}</p>
                  {locked && (
                    <span className="inline-block mt-1 text-[10px] font-semibold text-amber-600 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
                      Disabled for BFSI
                    </span>
                  )}
                </div>
              </label>
            )
          })}
        </div>

        {/* Fallback note */}
        <div className="flex gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5">
          <Info size={13} className="text-slate-400 mt-0.5 shrink-0" />
          <p className="text-xs text-slate-500 leading-4">
            If an employee record is missing data for a selected channel (e.g., no personal email on file),
            PRANA automatically falls back to the next available channel in the list above.
          </p>
        </div>

        {activeSmsButBfsi && (
          <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
            <AlertTriangle size={13} className="text-red-500 mt-0.5 shrink-0"/>
            <p className="text-xs text-red-600">SMS is not allowed for BFSI tenants. Remove it before saving.</p>
          </div>
        )}

        <div className="pt-1">
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || !dirty || activeSmsButBfsi || channels.size === 0}
            className="flex items-center gap-2 px-5 py-2.5 bg-violet-600 text-white
                       rounded-lg text-sm font-medium hover:bg-violet-700 disabled:opacity-40 transition-opacity"
          >
            {saved
              ? <><CheckCircle2 size={14}/> Saved</>
              : saveMutation.isPending
                ? 'Saving…'
                : <><Save size={14}/> Save settings</>
            }
          </button>
        </div>
      </div>

      {/* ── Re-send activation ── */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-3">
        <h2 className="font-medium text-slate-800">Re-send Activation</h2>
        <p className="text-xs text-slate-500">
          To re-send an activation credential to a specific employee, go to
          <strong className="text-slate-700"> Employee Master → employee row → Re-send activation</strong>.
          This uses the channels configured above.
        </p>
      </div>

      {/* ── Storage ── */}
      <div className="bg-white rounded-xl border border-red-100 shadow-sm p-6 space-y-4">
        <h2 className="font-medium text-red-700 flex items-center gap-2">
          <AlertTriangle size={16}/> Storage
        </h2>
        <p className="text-sm text-slate-500">Need additional storage capacity?</p>
        <button className="text-sm font-medium text-red-600 border border-red-200 px-4 py-2 rounded-lg hover:bg-red-50">
          Request storage expansion
        </button>
      </div>
    </div>
  )
}
