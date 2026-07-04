import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Key, Plus, Ban } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'
import { tUi } from '@/i18n'

export function ApiKeys() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ tenant_id: '', label: '', rate_limit_per_minute: 60 })

  const { data } = useQuery({
    queryKey: ['pa-api-keys'],
    queryFn: () => api.get('/admin/api-keys').then(r => r.data),
  })

  const createMut = useMutation({
    mutationFn: () => api.post('/admin/api-keys', form).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-api-keys'] })
      setShowForm(false)
      setForm({ tenant_id: '', label: '', rate_limit_per_minute: 60 })
    },
  })

  const revokeMut = useMutation({
    mutationFn: (id: string) => api.post(`/admin/api-keys/${id}/revoke`, {}).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pa-api-keys'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">{tUi('PA_API_KEYS_TITLE')}</h1>
        <button
          onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-1.5 text-xs bg-indigo-600 text-white rounded-lg px-3 py-2 hover:bg-indigo-700"
        >
          <Plus size={13} /> {tUi('PA_API_KEYS_ISSUE_KEY')}
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded-xl border border-indigo-100 shadow-sm p-6 space-y-4">
          <h2 className="font-medium text-slate-800">{tUi('PA_API_KEYS_ISSUE_NEW_TITLE')}</h2>
          <p className="text-xs text-slate-400">
            {tUi('PA_API_KEYS_DESC_PREFIX')} <code className="font-mono bg-slate-100 px-1 rounded">POST /ingest/upload</code>.
            {tUi('PA_API_KEYS_DESC_AUTH')} <code className="font-mono bg-slate-100 px-1 rounded">X-PRANA-Key-ID</code> + <code className="font-mono bg-slate-100 px-1 rounded">X-PRANA-Signature</code>.
          </p>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div>
              <label className="text-xs text-slate-500 block mb-1">{tUi('PA_API_KEYS_TENANT_LABEL')}</label>
              <select
                value={form.tenant_id}
                onChange={e => setForm(f => ({ ...f, tenant_id: e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              >
                <option value="">{tUi('PA_API_KEYS_SELECT_TENANT')}</option>
                {(data?.tenants ?? []).map((t: any) => (
                  <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500 block mb-1">{tUi('PA_API_KEYS_LABEL_LABEL')}</label>
              <input
                value={form.label}
                onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
                placeholder={tUi('PA_API_KEYS_LABEL_PLACEHOLDER')}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-slate-500 block mb-1">{tUi('PA_API_KEYS_RATE_LIMIT_LABEL')}</label>
              <input
                type="number"
                value={form.rate_limit_per_minute}
                onChange={e => setForm(f => ({ ...f, rate_limit_per_minute: +e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>
          {createMut.data?.api_key && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
              <p className="text-xs text-emerald-700 font-medium mb-1">{tUi('PA_API_KEYS_KEY_CREATED_NOTE')}</p>
              <code className="text-xs font-mono text-emerald-900 break-all">{createMut.data.api_key}</code>
            </div>
          )}
          {!createMut.data && (
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowForm(false)} className="text-xs text-slate-500 px-3 py-2">{tUi('EMP_SHARES_CANCEL')}</button>
              <button
                onClick={() => createMut.mutate()}
                disabled={!form.tenant_id || !form.label || createMut.isPending}
                className="text-xs bg-indigo-600 text-white rounded-lg px-4 py-2 hover:bg-indigo-700 disabled:opacity-50"
              >
                {createMut.isPending ? tUi('PA_API_KEYS_CREATING') : tUi('PA_API_KEYS_ISSUE_KEY')}
              </button>
            </div>
          )}
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
          <Key size={14} className="text-indigo-500" />
          <h2 className="font-medium text-slate-800">{tUi('PA_API_KEYS_ACTIVE_TITLE')}</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-slate-400 uppercase tracking-wide">
                <th className="px-5 py-3 text-left font-medium">Label</th>
                <th className="px-5 py-3 text-left font-medium">Tenant</th>
                <th className="px-5 py-3 text-left font-medium">Key ID (prefix)</th>
                <th className="px-5 py-3 text-right font-medium">Rate limit</th>
                <th className="px-5 py-3 text-right font-medium">Last used</th>
                <th className="px-5 py-3 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {(data?.keys ?? []).map((k: any) => (
                <tr key={k.api_key_id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3 font-medium text-slate-700">{k.label}</td>
                  <td className="px-5 py-3 text-slate-500">{k.tenant_name}</td>
                  <td className="px-5 py-3 font-mono text-xs text-slate-400">{k.key_id_prefix}…</td>
                  <td className="px-5 py-3 text-right font-mono text-slate-700">{k.rate_limit_per_minute}/min</td>
                  <td className="px-5 py-3 text-right text-xs text-slate-400 font-mono">
                    {k.last_used_at ? fmtDateTime(k.last_used_at) : tUi('PA_API_KEYS_NEVER')}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={() => revokeMut.mutate(k.api_key_id)}
                      disabled={revokeMut.isPending}
                      className="text-xs text-red-600 hover:text-red-800 font-medium flex items-center gap-1 ml-auto"
                    >
                      <Ban size={11} /> {tUi('CISO_SHARE_ANALYTICS_REVOKE')}
                    </button>
                  </td>
                </tr>
              ))}
              {!data?.keys?.length && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-sm text-slate-400">{tUi('PA_API_KEYS_NONE')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
