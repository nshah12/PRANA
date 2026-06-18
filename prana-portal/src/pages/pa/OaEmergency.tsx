import { useState } from 'react'
import { AlertTriangle, Zap } from 'lucide-react'
import { api } from '@/lib/api'

export function OaEmergency() {
  const [action, setAction] = useState<'create'|'suspend'|'reset'|null>(null)
  const [form, setForm] = useState({ email: '', tenant_domain: '', reason: '' })
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(''); setResult(null)
    try {
      const res = await api.post(`/admin/oa-emergency/${action}`, form)
      setResult(res.data.message ?? 'Done')
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Failed')
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">OA Emergency Override</h1>
        <div className="mt-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3 flex gap-2">
          <AlertTriangle size={15} className="text-red-600 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-red-700">
            Emergency actions only. Every action is tagged <span className="font-mono font-bold">PA_EMERGENCY_OVERRIDE</span> in the immutable audit log.
          </p>
        </div>
      </div>

      <div className="flex gap-2">
        {(['create','suspend','reset'] as const).map(a => (
          <button key={a} onClick={() => setAction(a)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    action === a ? 'bg-red-600 text-white border-red-600' : 'border-slate-200 text-slate-600 hover:border-red-400'
                  }`}>
            {a.charAt(0).toUpperCase() + a.slice(1)} OA
          </button>
        ))}
      </div>

      {action && (
        <form onSubmit={submit} className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-4">
          <h2 className="font-medium text-slate-800 flex items-center gap-2">
            <Zap size={14} className="text-red-500"/> {action.charAt(0).toUpperCase() + action.slice(1)} OA account
          </h2>
          {['email','tenant_domain','reason'].map(field => (
            <div key={field} className="space-y-1">
              <label className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                {field.replace('_',' ')} {field === 'reason' ? '*' : ''}
              </label>
              <input value={(form as any)[field]}
                     onChange={e => setForm(f => ({...f, [field]: e.target.value}))}
                     required={field === 'reason' || field === 'tenant_domain'}
                     className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm
                                focus:outline-none focus:ring-2 focus:ring-red-400" />
            </div>
          ))}
          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          {result && <p className="text-sm text-emerald-600 bg-emerald-50 rounded-lg px-3 py-2">{result}</p>}
          <button type="submit"
                  className="w-full bg-red-600 hover:bg-red-700 text-white font-medium py-2.5
                             rounded-lg transition-colors">
            Execute override
          </button>
        </form>
      )}
    </div>
  )
}
