import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Unlock } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi, tError, tSuccess } from '@/i18n'

export function PaUnlock() {
  const [email, setEmail] = useState('')
  const [result, setResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  const mutation = useMutation({
    mutationFn: (email: string) => api.post('/admin/pa-users/unlock', { email }),
    onSuccess: (res) => {
      setResult({ type: 'success', message: tSuccess(res.data.message) })
      setEmail('')
    },
    onError: (e: any) => {
      setResult({ type: 'error', message: tError(e.response?.data?.detail) })
    },
  })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setResult(null)
    if (!email.trim()) return
    if (!confirm(tUi('PA_UNLOCK_CONFIRM'))) return
    mutation.mutate(email.trim())
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">{tUi('PA_UNLOCK_TITLE')}</h1>
        <p className="text-sm text-slate-500 mt-1">{tUi('PA_UNLOCK_SUB')}</p>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1">
            <label htmlFor="pa-unlock-email"
                   className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              {tUi('PA_UNLOCK_EMAIL_LABEL')}
            </label>
            <input
              id="pa-unlock-email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="name@prana.in"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm
                         focus:outline-none focus:ring-1 focus:ring-violet-500"
              required
            />
          </div>

          {result && (
            <p className={`text-sm rounded-lg px-3 py-2 ${
              result.type === 'success'
                ? 'text-emerald-700 bg-emerald-50'
                : 'text-red-600 bg-red-50'
            }`}>
              {result.message}
            </p>
          )}

          <button
            type="submit"
            disabled={mutation.isPending || !email.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white
                       rounded-lg text-sm font-medium hover:bg-violet-700
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Unlock size={14}/> {tUi('PA_UNLOCK_SUBMIT_BTN')}
          </button>
        </form>
      </div>
    </div>
  )
}
