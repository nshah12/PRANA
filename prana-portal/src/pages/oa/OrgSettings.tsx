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
import { tUi } from '@/i18n'

type Channel = 'personal_email' | 'work_email' | 'sms'

function getChannelMeta(): Record<Channel, { label: string; desc: string; bfsiAllowed: boolean }> {
  return {
    personal_email: {
      label: tUi('OA_ORG_SETTINGS_CH_PERSONAL_EMAIL_LABEL'),
      desc: tUi('OA_ORG_SETTINGS_CH_PERSONAL_EMAIL_DESC'),
      bfsiAllowed: true,
    },
    work_email: {
      label: tUi('OA_ORG_SETTINGS_CH_WORK_EMAIL_LABEL'),
      desc: tUi('OA_ORG_SETTINGS_CH_WORK_EMAIL_DESC'),
      bfsiAllowed: true,
    },
    sms: {
      label: tUi('OA_ORG_SETTINGS_CH_SMS_LABEL'),
      desc: tUi('OA_ORG_SETTINGS_CH_SMS_DESC'),
      bfsiAllowed: false,
    },
  }
}

function parseChannels(raw: string | undefined): Set<Channel> {
  if (!raw) return new Set(['personal_email'])
  return new Set(raw.split(',').filter(Boolean) as Channel[])
}

export function OrgSettings() {
  const { data } = useQuery({
    queryKey: ['org-settings'],
    queryFn: () => api.get('/v1/org/settings').then(r => r.data),
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
  const CHANNEL_META = getChannelMeta()

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
    mutationFn: () => api.patch('/v1/org/settings', {
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
        <Settings size={18} /> {tUi('OA_ORG_SETTINGS_TITLE')}
      </h1>

      {isBfsi && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex gap-2">
          <AlertTriangle size={15} className="text-amber-600 mt-0.5 shrink-0" />
          <p className="text-xs text-amber-700">
            <strong>{tUi('OA_ORG_SETTINGS_BFSI_BOLD')}</strong> {tUi('OA_ORG_SETTINGS_BFSI_NOTE')}
          </p>
        </div>
      )}

      {/* ── Employee Activation Channels ── */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-5">
        <div>
          <h2 className="font-medium text-slate-800">{tUi('OA_ORG_SETTINGS_ACTIVATION_CHANNELS_TITLE')}</h2>
          <p className="text-xs text-slate-500 mt-1">
            {tUi('OA_ORG_SETTINGS_ACTIVATION_CHANNELS_SUB')}
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
                      {tUi('OA_ORG_SETTINGS_DISABLED_BFSI')}
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
            {tUi('OA_ORG_SETTINGS_FALLBACK_NOTE')}
          </p>
        </div>

        {activeSmsButBfsi && (
          <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
            <AlertTriangle size={13} className="text-red-500 mt-0.5 shrink-0"/>
            <p className="text-xs text-red-600">{tUi('OA_ORG_SETTINGS_SMS_BFSI_ERROR')}</p>
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
              ? <><CheckCircle2 size={14}/> {tUi('OA_ORG_PROFILE_SAVED')}</>
              : saveMutation.isPending
                ? tUi('OA_ORG_PROFILE_SAVING')
                : <><Save size={14}/> {tUi('OA_ORG_SETTINGS_SAVE_BTN')}</>
            }
          </button>
        </div>
      </div>

      {/* ── Re-send activation ── */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-3">
        <h2 className="font-medium text-slate-800">{tUi('OA_ORG_SETTINGS_RESEND_TITLE')}</h2>
        <p className="text-xs text-slate-500">
          {tUi('OA_ORG_SETTINGS_RESEND_TEXT_PREFIX')}
          <strong className="text-slate-700"> {tUi('OA_ORG_SETTINGS_RESEND_TEXT_BOLD')}</strong>{tUi('OA_ORG_SETTINGS_RESEND_TEXT_SUFFIX')}
        </p>
      </div>

      {/* ── Storage ── */}
      <div className="bg-white rounded-xl border border-red-100 shadow-sm p-6 space-y-4">
        <h2 className="font-medium text-red-700 flex items-center gap-2">
          <AlertTriangle size={16}/> {tUi('OA_ORG_SETTINGS_STORAGE_TITLE')}
        </h2>
        <p className="text-sm text-slate-500">{tUi('OA_ORG_SETTINGS_STORAGE_QUESTION')}</p>
        <button className="text-sm font-medium text-red-600 border border-red-200 px-4 py-2 rounded-lg hover:bg-red-50">
          {tUi('OA_ORG_SETTINGS_STORAGE_REQUEST_BTN')}
        </button>
      </div>
    </div>
  )
}
