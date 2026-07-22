import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { UserPlus, Shield, UserX, MailPlus } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDate } from '@/lib/utils'
import { tUi, tError, tSuccess } from '@/i18n'

const ROLES = ['oa_operator', 'oa_admin', 'chro', 'cfo', 'ciso'] as const

export function UserManagement() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['oa-users'],
    queryFn: () => api.get('/v1/org/users').then(r => r.data),
  })

  const deactivateMutation = useMutation({
    mutationFn: (userId: string) => api.delete(`/v1/org/users/${userId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['oa-users'] }),
    onError: (e: any) => {
      if (e.response?.data?.detail === 'MIN_ADMIN_CONSTRAINT') {
        alert(tUi('OA_USER_MGMT_CANNOT_DEACTIVATE'))
      }
    },
  })

  const changeRoleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      api.patch(`/v1/org/users/${userId}/role`, { role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['oa-users'] }),
    onError: (e: any) => {
      if (e.response?.data?.detail === 'MIN_ADMIN_CONSTRAINT') {
        alert(tUi('OA_USER_MGMT_CANNOT_DEMOTE'))
      }
    },
  })

  const resendWelcomeMutation = useMutation({
    mutationFn: (userId: string) => api.post(`/v1/org/users/${userId}/resend-welcome`),
    onSuccess: (res) => alert(tSuccess(res.data.message)),
    onError: (e: any) => alert(tError(e.response?.data?.detail)),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">{tUi('OA_USER_MGMT_TITLE')}</h1>
        <button onClick={() => setShowCreate(true)}
                className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white
                           rounded-lg text-sm font-medium hover:bg-violet-700">
          <UserPlus size={14}/> {tUi('OA_USER_MGMT_INVITE_USER')}
        </button>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex gap-2">
        <Shield size={15} className="text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-xs text-amber-700">
          {tUi('OA_USER_MGMT_MIN_ADMIN_NOTE')}
        </p>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_USER_MGMT_COL_NAME_EMAIL')}</th>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_USER_MGMT_COL_ROLE')}</th>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_USER_MGMT_COL_STATUS')}</th>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_USER_MGMT_COL_CREATED')}</th>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_USER_MGMT_COL_ACTIONS')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading && (
              <tr><td colSpan={5} className="px-5 py-8 text-center text-slate-400">{tUi('CFO_DIGEST_LOADING')}</td></tr>
            )}
            {!isLoading && isError && (
              <tr><td colSpan={5} className="px-5 py-8 text-center text-red-500">{tUi('OA_USER_MGMT_LOAD_FAILED')}</td></tr>
            )}
            {!isLoading && !isError && (data?.users?.length ?? 0) === 0 && (
              <tr><td colSpan={5} className="px-5 py-8 text-center text-slate-400">{tUi('OA_USER_MGMT_NONE_FOUND')}</td></tr>
            )}
            {!isLoading && !isError && data?.users?.map((u: any) => (
              <tr key={u.oa_user_id} className="hover:bg-canvas2">
                <td className="px-5 py-3">
                  <p className="font-medium text-slate-800">{u.display_name}</p>
                  <p className="text-xs text-slate-400 font-mono">{u.email}</p>
                </td>
                <td className="px-5 py-3">
                  <select
                    value={u.role}
                    onChange={e => changeRoleMutation.mutate({ userId: u.oa_user_id, role: e.target.value })}
                    className="border border-slate-200 rounded-md px-2 py-1 text-xs bg-white
                               focus:outline-none focus:ring-1 focus:ring-violet-500"
                  >
                    {ROLES.map(r => (
                      <option key={r} value={r}>{r.replace(/_/g, ' ').toUpperCase()}</option>
                    ))}
                  </select>
                </td>
                <td className="px-5 py-3">
                  <StatusBadge status={u.status} />
                </td>
                <td className="px-5 py-3 text-xs text-slate-400">{fmtDate(u.created_at)}</td>
                <td className="px-5 py-3">
                  <div className="flex flex-col gap-1 items-start">
                    <button onClick={() => resendWelcomeMutation.mutate(u.oa_user_id)}
                            className="flex items-center gap-1 text-xs text-sky-600 hover:underline">
                      <MailPlus size={13}/> {tUi('OA_USER_MGMT_RESEND_WELCOME_BTN')}
                    </button>
                    {u.status === 'ACTIVE' && (
                      <button onClick={() => {
                        if (confirm(tUi('OA_USER_MGMT_DEACTIVATE_CONFIRM', { name: u.display_name }))) {
                          deactivateMutation.mutate(u.oa_user_id)
                        }
                      }}
                      className="flex items-center gap-1 text-xs text-red-500 hover:underline">
                        <UserX size={13}/> {tUi('OA_USER_MGMT_DEACTIVATE_BTN')}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && <CreateUserModal onClose={() => setShowCreate(false)} />}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    ACTIVE: 'badge-emerald', INACTIVE: 'badge-muted',
    LOCKED: 'badge-red', PENDING: 'badge-amber',
  }
  return <span className={`badge ${map[status] ?? 'badge-muted'}`}>{status}</span>
}

function CreateUserModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ display_name: '', email: '', role: 'oa_operator' })
  const [error, setError] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await api.post('/v1/org/users', form)
      qc.invalidateQueries({ queryKey: ['oa-users'] })
      onClose()
    } catch (e: any) {
      setError(e.response?.data?.detail ?? tUi('OA_USER_MGMT_CREATE_FAILED'))
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-end md:items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-[520px] shadow-2xl">
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-100">
          <h2 className="font-semibold text-slate-800">{tUi('OA_USER_MGMT_INVITE_USER')}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          <Field label={tUi('OA_USER_MGMT_FULL_NAME_LABEL')}>
            <input value={form.display_name} onChange={e => setForm(f => ({...f, display_name: e.target.value}))}
                   required className="input" />
          </Field>
          <Field label={tUi('OA_USER_MGMT_WORK_EMAIL_LABEL')}>
            <input type="email" value={form.email}
                   onChange={e => setForm(f => ({...f, email: e.target.value}))}
                   required className="input" />
          </Field>
          <Field label={tUi('OA_USER_MGMT_ROLE_LABEL')}>
            <select value={form.role} onChange={e => setForm(f => ({...f, role: e.target.value}))}
                    className="input bg-white">
              {['oa_operator','oa_admin','chro','cfo','ciso'].map(r => (
                <option key={r} value={r}>{r.replace(/_/g,' ').toUpperCase()}</option>
              ))}
            </select>
          </Field>
          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2 justify-end">
            <button type="button" onClick={onClose}
                    className="px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-canvas2">
              {tUi('EMP_SHARES_CANCEL')}
            </button>
            <button type="submit"
                    className="px-4 py-2 text-sm bg-violet-600 text-white rounded-lg hover:bg-violet-700">
              {tUi('OA_USER_MGMT_INVITE_BTN')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</label>
      {children}
    </div>
  )
}
