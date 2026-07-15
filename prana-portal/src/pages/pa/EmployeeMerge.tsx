import { useState } from 'react'
import { AlertTriangle, GitMerge } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi, tError, tSuccess } from '@/i18n'

export function EmployeeMerge() {
  const [form, setForm] = useState({ duplicate_identifier: '', canonical_identifier: '', reason: '' })
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(''); setResult(null)
    try {
      const res = await api.post('/admin/employees/merge', form)
      setResult(tSuccess(res.data.message))
      setForm({ duplicate_identifier: '', canonical_identifier: '', reason: '' })
    } catch (e: any) {
      setError(tError(e.response?.data?.detail))
    }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">{tUi('PA_EMPLOYEE_MERGE_TITLE')}</h1>
        <div className="mt-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3 flex gap-2">
          <AlertTriangle size={15} className="text-red-600 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-red-700">
            {tUi('PA_EMPLOYEE_MERGE_WARNING_PREFIX')} <span className="font-mono font-bold">PORTAL_ADMIN</span> {tUi('PA_EMPLOYEE_MERGE_WARNING_SUFFIX')}
          </p>
        </div>
      </div>

      <form onSubmit={submit} className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-4">
        <h2 className="font-medium text-slate-800 flex items-center gap-2">
          <GitMerge size={14} className="text-red-500"/> {tUi('PA_EMPLOYEE_MERGE_SECTION_TITLE')}
        </h2>

        <div className="space-y-1">
          <label htmlFor="merge-duplicate"
                 className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            {tUi('PA_EMPLOYEE_MERGE_DUPLICATE_LABEL')}
          </label>
          <input
            id="merge-duplicate"
            value={form.duplicate_identifier}
            onChange={e => setForm(f => ({...f, duplicate_identifier: e.target.value}))}
            placeholder={tUi('OA_RESET_TOTP_IDENTIFIER_PLACEHOLDER')}
            required
            className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm
                       focus:outline-none focus:ring-2 focus:ring-red-400"
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="merge-canonical"
                 className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            {tUi('PA_EMPLOYEE_MERGE_CANONICAL_LABEL')}
          </label>
          <input
            id="merge-canonical"
            value={form.canonical_identifier}
            onChange={e => setForm(f => ({...f, canonical_identifier: e.target.value}))}
            placeholder={tUi('OA_RESET_TOTP_IDENTIFIER_PLACEHOLDER')}
            required
            className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm
                       focus:outline-none focus:ring-2 focus:ring-red-400"
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="merge-reason"
                 className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            {tUi('PA_RESET_TOTP_REASON_LABEL')} *
          </label>
          <input
            id="merge-reason"
            value={form.reason}
            onChange={e => setForm(f => ({...f, reason: e.target.value}))}
            required
            className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm
                       focus:outline-none focus:ring-2 focus:ring-red-400"
          />
        </div>

        {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
        {result && <p className="text-sm text-emerald-600 bg-emerald-50 rounded-lg px-3 py-2">{result}</p>}

        <button type="submit"
                className="w-full bg-red-600 hover:bg-red-700 text-white font-medium py-2.5
                           rounded-lg transition-colors">
          {tUi('PA_EMPLOYEE_MERGE_EXECUTE_BTN')}
        </button>
      </form>
    </div>
  )
}
