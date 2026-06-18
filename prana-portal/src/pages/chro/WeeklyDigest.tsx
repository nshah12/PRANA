import { useQuery, useMutation } from '@tanstack/react-query'
import { Send, Mail } from 'lucide-react'
import { api } from '@/lib/api'

export function WeeklyDigest() {
  const { data } = useQuery({
    queryKey: ['chro-weekly-digest'],
    queryFn: () => api.get('/v1/chro/digest/weekly').then(r => r.data),
  })

  const sendTest = useMutation({
    mutationFn: () => api.post('/v1/chro/digest/weekly/send-test'),
  })

  return (
    <div className="space-y-6 max-w-xl">
      <h1 className="text-xl font-semibold text-slate-800">Weekly Digest</h1>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-5">
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">Sent every <strong>Monday 6:00 AM IST</strong></p>
          <button onClick={() => sendTest.mutate()}
                  disabled={sendTest.isPending}
                  className="flex items-center gap-2 text-sm font-medium text-violet-600
                             border border-violet-200 px-3 py-1.5 rounded-lg hover:bg-violet-50">
            <Send size={13}/> {sendTest.isPending ? 'Sending…' : 'Send test'}
          </button>
        </div>

        {/* Preview */}
        <div className="border border-slate-200 rounded-xl overflow-hidden">
          <div className="bg-shell px-5 py-3 flex items-center gap-2">
            <Mail size={14} className="text-slate-400" />
            <span className="text-xs font-mono text-slate-400">Preview — Monday digest</span>
          </div>
          <div className="p-5 space-y-4 text-sm text-slate-700">
            <p className="font-semibold text-base">PRANA Weekly Digest</p>
            <div className="grid grid-cols-2 gap-3">
              {[
                ['Vault health', data?.overall_score ? `${data.overall_score}%` : '—'],
                ['Docs pushed', data?.docs_pushed_this_week ?? '—'],
                ['Open exceptions', data?.open_exceptions ?? '—'],
                ['Next deadline', data?.next_deadline ? `${data.next_deadline.deadline} — ${data.next_deadline.name}` : '—'],
              ].map(([k, v]) => (
                <div key={k} className="bg-canvas2 rounded-lg p-3">
                  <p className="text-xs text-slate-400">{k}</p>
                  <p className="font-semibold font-mono text-slate-800 mt-0.5">{v}</p>
                </div>
              ))}
            </div>
            {data?.risk_flag && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                <p className="text-xs font-medium text-amber-700">⚠ {data.risk_flag}</p>
              </div>
            )}
          </div>
        </div>

        {/* Channel prefs */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Delivery channel</p>
          <div className="flex gap-2">
            {['Email', 'WhatsApp', 'In-app'].map(ch => (
              <label key={ch} className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                <input type="checkbox" defaultChecked={ch !== 'WhatsApp'}
                       className="accent-violet-600" />
                {ch}
              </label>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
