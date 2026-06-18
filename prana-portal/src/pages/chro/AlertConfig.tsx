import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Bell } from 'lucide-react'
import { api } from '@/lib/api'

const ALERT_TYPES = [
  { id: 'deadline_alert',    label: 'Statutory deadline alert',   description: 'Notifies when a Labour/IT/DPDP deadline is < 30 days away' },
  { id: 'vault_health_drop', label: 'Vault health drop',          description: 'Notifies when org-wide vault completeness drops more than 5 points' },
  { id: 'exception_spike',   label: 'Exception queue spike',       description: 'Notifies when > 5 exceptions remain open (SLA breach risk)' },
  { id: 'exit_doc_delay',    label: 'Exit document delay',         description: 'Notifies when relieving/experience letter not pushed within 7 days of exit' },
  { id: 'security_anomaly',  label: 'Security anomaly (P0/P1)',    description: 'Notifies CHRO on critical security anomaly — off by default' },
]

export function AlertConfig() {
  const qc = useQueryClient()

  const { data: configData, isLoading } = useQuery({
    queryKey: ['chro-alert-config'],
    queryFn: () => api.get('/v1/chro/alerts/config').then(r => r.data),
  })

  const [config, setConfig] = useState<Record<string, boolean>>(
    Object.fromEntries(ALERT_TYPES.map(a => [a.id, true]))
  )
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (configData?.config) {
      setConfig(configData.config)
    }
  }, [configData])

  const saveMutation = useMutation({
    mutationFn: (cfg: Record<string, boolean>) =>
      api.patch('/v1/chro/alerts/config', { config: cfg }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chro-alert-config'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  function toggle(id: string) {
    setConfig(c => ({ ...c, [id]: !c[id] }))
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Alert Configuration</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Choose which events trigger notifications to your email, WhatsApp, and in-app inbox.
          Preferences are saved per organisation.
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-3 animate-pulse">
          {[...Array(5)].map((_, i) => <div key={i} className="h-16 bg-slate-100 rounded-xl" />)}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-4">
          <h2 className="font-medium text-slate-700 text-sm flex items-center gap-2">
            <Bell size={14}/> Alert types
          </h2>
          {ALERT_TYPES.map(alert => (
            <div key={alert.id} className="flex items-start justify-between py-3 border-b border-slate-50 last:border-0 gap-4">
              <div className="flex-1">
                <p className="text-sm font-medium text-slate-700">{alert.label}</p>
                <p className="text-xs text-slate-400 mt-0.5">{alert.description}</p>
                <p className="text-xs text-slate-300 mt-0.5">Email + WhatsApp + In-app</p>
              </div>
              <button
                onClick={() => toggle(alert.id)}
                className={`relative w-11 h-6 rounded-full transition-colors flex-shrink-0 mt-0.5 ${
                  config[alert.id] ? 'bg-pink-500' : 'bg-slate-200'
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow
                                 transition-transform ${config[alert.id] ? 'translate-x-5' : ''}`} />
              </button>
            </div>
          ))}

          <button
            onClick={() => saveMutation.mutate(config)}
            disabled={saveMutation.isPending}
            className="flex items-center gap-2 px-5 py-2.5 bg-pink-600 text-white
                       rounded-lg text-sm font-medium hover:bg-pink-700 disabled:opacity-40"
          >
            <Save size={14}/>
            {saveMutation.isPending ? 'Saving…' : saved ? 'Saved ✓' : 'Save configuration'}
          </button>
          {saveMutation.isError && (
            <p className="text-xs text-red-600">Failed to save. Please try again.</p>
          )}
        </div>
      )}
    </div>
  )
}
