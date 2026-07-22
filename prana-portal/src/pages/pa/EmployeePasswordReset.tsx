import { useState } from 'react'
import { AlertTriangle, KeyRound } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi, tError, tSuccess } from '@/i18n'
import { OverrideReasonFields } from '@/components/OverrideReasonFields'

export function EmployeePasswordReset() {
  const [form, setForm] = useState({ identifier: '', reasonCode: '', reasonNote: '' })
  const [result, setResult] = useState<string | null>(null)
  const [tempPassword, setTempPassword] = useState<string | null>(null)
  const [error, setError] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(''); setResult(null); setTempPassword(null)
    try {
      const res = await api.post('/admin/employees/reset-password', {
        identifier: form.identifier,
        reason_code: form.reasonCode,
        reason_note: form.reasonNote.trim() || null,
      })
      setResult(tSuccess(res.data.message))
      setTempPassword(res.data.temp_password ?? null)
      setForm({ identifier: '', reasonCode: '', reasonNote: '' })
    } catch (e: any) {
      setError(tError(e.response?.data?.detail))
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">{tUi('PA_RESET_PASSWORD_TITLE')}</h1>
        <div className="mt-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3 flex gap-2">
          <AlertTriangle size={15} className="text-red-600 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-red-700">
            {tUi('PA_RESET_TOTP_WARNING_PREFIX')} <span className="font-mono font-bold">PORTAL_ADMIN</span> {tUi('PA_RESET_TOTP_WARNING_SUFFIX')}
          </p>
        </div>
      </div>

      <form onSubmit={submit} className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-4">
        <h2 className="font-medium text-slate-800 flex items-center gap-2">
          <KeyRound size={14} className="text-red-500"/> {tUi('PA_RESET_PASSWORD_SECTION_TITLE')}
        </h2>

        <div className="space-y-1">
          <label htmlFor="pa-reset-password-identifier"
                 className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            {tUi('PA_RESET_TOTP_IDENTIFIER_LABEL')}
          </label>
          <input
            id="pa-reset-password-identifier"
            value={form.identifier}
            onChange={e => setForm(f => ({...f, identifier: e.target.value}))}
            placeholder={tUi('OA_RESET_TOTP_IDENTIFIER_PLACEHOLDER')}
            required
            className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm
                       focus:outline-none focus:ring-2 focus:ring-red-400"
          />
        </div>

        <OverrideReasonFields
          idPrefix="pa-reset-password"
          reasonCode={form.reasonCode}
          reasonNote={form.reasonNote}
          onReasonCodeChange={code => setForm(f => ({...f, reasonCode: code}))}
          onReasonNoteChange={note => setForm(f => ({...f, reasonNote: note}))}
        />

        {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
        {result && (
          <div className="text-sm text-emerald-600 bg-emerald-50 rounded-lg px-3 py-2 space-y-2">
            <p>{result}</p>
            {tempPassword && (
              <p className="font-mono font-bold text-slate-800 bg-white rounded px-2 py-1 border border-emerald-200">
                {tempPassword}
              </p>
            )}
          </div>
        )}

        <button type="submit"
                className="w-full bg-red-600 hover:bg-red-700 text-white font-medium py-2.5
                           rounded-lg transition-colors">
          {tUi('PA_RESET_TOTP_EXECUTE_BTN')}
        </button>
      </form>
    </div>
  )
}
