import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { KeyRound } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi, tError, tSuccess } from '@/i18n'

export function EmployeePasswordReset() {
  const [identifier, setIdentifier] = useState('')
  const [result, setResult] = useState<{ type: 'success' | 'error'; message: string; tempPassword?: string } | null>(null)

  const mutation = useMutation({
    mutationFn: (id: string) => api.post('/v1/org/employees/reset-password', { identifier: id }),
    onSuccess: (res) => {
      setResult({ type: 'success', message: tSuccess(res.data.message), tempPassword: res.data.temp_password })
      setIdentifier('')
    },
    onError: (e: any) => {
      setResult({ type: 'error', message: tError(e.response?.data?.detail) })
    },
  })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setResult(null)
    if (!identifier.trim()) return
    if (!confirm(tUi('OA_RESET_PASSWORD_CONFIRM'))) return
    mutation.mutate(identifier.trim())
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">{tUi('OA_RESET_PASSWORD_TITLE')}</h1>
        <p className="text-sm text-slate-500 mt-1">{tUi('OA_RESET_PASSWORD_SUB')}</p>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1">
            <label htmlFor="reset-password-identifier"
                   className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              {tUi('OA_RESET_PASSWORD_IDENTIFIER_LABEL')}
            </label>
            <input
              id="reset-password-identifier"
              value={identifier}
              onChange={e => setIdentifier(e.target.value)}
              placeholder={tUi('OA_RESET_TOTP_IDENTIFIER_PLACEHOLDER')}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm
                         focus:outline-none focus:ring-1 focus:ring-violet-500"
              required
            />
          </div>

          {result && (
            <div className={`text-sm rounded-lg px-3 py-2 space-y-2 ${
              result.type === 'success'
                ? 'text-emerald-700 bg-emerald-50'
                : 'text-red-600 bg-red-50'
            }`}>
              <p>{result.message}</p>
              {result.tempPassword && (
                <p className="font-mono font-bold text-slate-800 bg-white rounded px-2 py-1 border border-emerald-200">
                  {result.tempPassword}
                </p>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={mutation.isPending || !identifier.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white
                       rounded-lg text-sm font-medium hover:bg-violet-700
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <KeyRound size={14}/> {tUi('OA_RESET_PASSWORD_SUBMIT_BTN')}
          </button>
        </form>
      </div>
    </div>
  )
}
