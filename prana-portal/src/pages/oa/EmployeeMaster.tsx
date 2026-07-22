import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Search, Upload, UserPlus, RotateCcw, LogOut, Link2Off } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDate } from '@/lib/utils'
import { tUi, tError, tSuccess } from '@/i18n'

export function EmployeeMaster() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [showImport, setShowImport] = useState(false)
  const limit = 20
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['employees', search, page],
    queryFn: () => api.get('/v1/org/employees', {
      params: { name: search || undefined, limit, active_only: false },
    }).then(r => {
      // API returns a plain array; normalise to { employees, count }
      const arr: any[] = Array.isArray(r.data) ? r.data : (r.data.employees ?? [])
      const offset = page * limit
      return { employees: arr.slice(offset, offset + limit), count: arr.length, _all: arr }
    }),
    placeholderData: prev => prev,
  })

  const reactivateMutation = useMutation({
    mutationFn: (employeeUuid: string) => api.post(`/v1/org/employees/${employeeUuid}/reactivate`),
    onSuccess: (res) => {
      alert(tSuccess(res.data.message))
      qc.invalidateQueries({ queryKey: ['employees'] })
    },
    onError: (e: any) => {
      alert(tError(e.response?.data?.detail))
    },
  })

  function handleReactivate(employeeUuid: string, fullName: string) {
    if (confirm(tUi('OA_EMP_MASTER_REACTIVATE_CONFIRM', { name: fullName }))) {
      reactivateMutation.mutate(employeeUuid)
    }
  }

  const revokeSessionsMutation = useMutation({
    mutationFn: (employeeUuid: string) => api.post(`/v1/org/employees/${employeeUuid}/revoke-sessions`),
    onSuccess: (res) => {
      alert(tSuccess(res.data.message))
    },
    onError: (e: any) => {
      alert(tError(e.response?.data?.detail))
    },
  })

  function handleRevokeSessions(employeeUuid: string, fullName: string) {
    if (confirm(tUi('OA_EMP_MASTER_REVOKE_SESSIONS_CONFIRM', { name: fullName }))) {
      revokeSessionsMutation.mutate(employeeUuid)
    }
  }

  const revokeSharesMutation = useMutation({
    mutationFn: (employeeUuid: string) => api.post(`/v1/org/employees/${employeeUuid}/revoke-shares`),
    onSuccess: (res) => {
      alert(tSuccess(res.data.message))
    },
    onError: (e: any) => {
      alert(tError(e.response?.data?.detail))
    },
  })

  function handleRevokeShares(employeeUuid: string, fullName: string) {
    if (confirm(tUi('OA_EMP_MASTER_REVOKE_SHARES_CONFIRM', { name: fullName }))) {
      revokeSharesMutation.mutate(employeeUuid)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-slate-800">{tUi('OA_EMP_MASTER_TITLE')}</h1>
        <div className="flex gap-2">
          <button onClick={() => setShowImport(true)}
                  className="flex items-center gap-2 px-4 py-2 border border-slate-200
                             rounded-lg text-sm font-medium text-slate-600 hover:bg-canvas2">
            <Upload size={14}/> {tUi('OA_EMP_MASTER_BULK_UPLOAD')}
          </button>
          <button className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white
                             rounded-lg text-sm font-medium hover:bg-violet-700">
            <UserPlus size={14}/> {tUi('OA_EMP_MASTER_ADD_EMPLOYEE')}
          </button>
        </div>
      </div>

      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(0) }}
               placeholder={tUi('OA_EMP_MASTER_SEARCH_PLACEHOLDER')}
               className="w-full pl-9 pr-4 py-2.5 border border-slate-200 rounded-lg text-sm
                          focus:outline-none focus:ring-2 focus:ring-violet-500" />
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_EMP_MASTER_COL_NAME')}</th>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_EMP_MASTER_COL_EMP_ID')}</th>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_EMP_MASTER_COL_DEPARTMENT')}</th>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_EMP_MASTER_COL_DESIGNATION')}</th>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_EMP_MASTER_COL_DOJ')}</th>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_EMP_MASTER_COL_STATUS')}</th>
              <th className="text-left px-5 py-3 font-medium">{tUi('OA_EMP_MASTER_COL_ACTIONS')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading && (
              <tr><td colSpan={7} className="px-5 py-8 text-center text-slate-400">{tUi('CFO_DIGEST_LOADING')}</td></tr>
            )}
            {!isLoading && data?.employees?.length === 0 && (
              <tr><td colSpan={7} className="px-5 py-8 text-center text-slate-400">{tUi('EMPLOYEE_MASTER_NONE_FOUND')}</td></tr>
            )}
            {data?.employees?.map((emp: any) => (
              <tr key={emp.employee_uuid} className="hover:bg-canvas2 cursor-pointer">
                <td className="px-5 py-3 font-medium text-slate-800">{emp.full_name}</td>
                <td className="px-5 py-3 font-mono text-xs text-slate-500">{emp.emp_id_org ?? '—'}</td>
                <td className="px-5 py-3 text-slate-600">{emp.department ?? '—'}</td>
                <td className="px-5 py-3 text-slate-600">{emp.designation ?? '—'}</td>
                <td className="px-5 py-3 text-slate-500">{fmtDate(emp.doj)}</td>
                <td className="px-5 py-3">
                  <StatusBadge status={emp.status} />
                </td>
                <td className="px-5 py-3">
                  <div className="flex flex-col gap-1 items-start">
                    {emp.status === 'ALUMNI' && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleReactivate(emp.employee_uuid, emp.full_name) }}
                        className="flex items-center gap-1 text-xs text-sky-600 hover:underline"
                      >
                        <RotateCcw size={13}/> {tUi('OA_EMP_MASTER_REACTIVATE_BTN')}
                      </button>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRevokeSessions(emp.employee_uuid, emp.full_name) }}
                      className="flex items-center gap-1 text-xs text-red-500 hover:underline"
                    >
                      <LogOut size={13}/> {tUi('OA_EMP_MASTER_REVOKE_SESSIONS_BTN')}
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRevokeShares(emp.employee_uuid, emp.full_name) }}
                      className="flex items-center gap-1 text-xs text-red-500 hover:underline"
                    >
                      <Link2Off size={13}/> {tUi('OA_EMP_MASTER_REVOKE_SHARES_BTN')}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        {(data?.count ?? 0) > limit && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100">
            <span className="text-xs text-slate-400">
              {tUi('OA_EMP_MASTER_SHOWING', { from: page * limit + 1, to: Math.min((page + 1) * limit, data?.count ?? 0), total: data?.count ?? 0 })}
            </span>
            <div className="flex gap-2">
              <button onClick={() => setPage(p => p - 1)} disabled={page === 0}
                      className="text-xs px-3 py-1 border border-slate-200 rounded disabled:opacity-40
                                 hover:bg-canvas2">{tUi('OA_EMP_MASTER_PREV')}</button>
              <button onClick={() => setPage(p => p + 1)}
                      disabled={(page + 1) * limit >= (data?.count ?? 0)}
                      className="text-xs px-3 py-1 border border-slate-200 rounded disabled:opacity-40
                                 hover:bg-canvas2">{tUi('OA_EMP_MASTER_NEXT')}</button>
            </div>
          </div>
        )}
      </div>

      {showImport && (
        <BulkImportModal
          onClose={() => setShowImport(false)}
          onDone={() => qc.invalidateQueries({ queryKey: ['employees'] })}
        />
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    ACTIVE: 'badge-emerald', ALUMNI: 'badge-muted',
    PENDING_ACTIVATION: 'badge-amber', SUSPENDED: 'badge-red',
  }
  return <span className={`badge ${map[status] ?? 'badge-muted'}`}>{status}</span>
}

interface ImportError { row: number; error: string }
interface ImportResult { total: number; created: number; failed: number; errors: ImportError[] }

function BulkImportModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!file) return
    setError(''); setResult(null); setBusy(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await api.post('/v1/org/employees/import', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setResult(res.data)
      if (res.data.created > 0) onDone()
    } catch (e: any) {
      setError(tError(e.response?.data?.detail))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-end md:items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-[560px] shadow-2xl">
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-100">
          <h2 className="font-semibold text-slate-800">{tUi('OA_EMP_MASTER_BULK_UPLOAD')}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          <p className="text-xs text-slate-500">{tUi('OA_EMP_MASTER_IMPORT_HELP')}</p>
          <input
            type="file"
            accept=".csv,text/csv"
            aria-label={tUi('OA_EMP_MASTER_IMPORT_FILE_LABEL')}
            onChange={e => setFile(e.target.files?.[0] ?? null)}
            className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2"
          />

          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}

          {result && (
            <div className="space-y-2">
              <p className="text-sm text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">
                {tSuccess('EMPLOYEE_BULK_IMPORT_COMPLETE')}{' '}
                {tUi('OA_EMP_MASTER_IMPORT_SUMMARY', { created: result.created, total: result.total, failed: result.failed })}
              </p>
              {result.errors.length > 0 && (
                <div className="max-h-40 overflow-y-auto border border-slate-100 rounded-lg">
                  <table className="w-full text-xs">
                    <thead className="bg-canvas2 text-slate-500 uppercase">
                      <tr>
                        <th className="text-left px-3 py-2">{tUi('OA_EMP_MASTER_IMPORT_ROW_COL')}</th>
                        <th className="text-left px-3 py-2">{tUi('OA_EMP_MASTER_IMPORT_ERROR_COL')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {result.errors.map((err, i) => (
                        <tr key={i}>
                          <td className="px-3 py-1.5 font-mono">{err.row}</td>
                          <td className="px-3 py-1.5 text-red-600">{tError(err.error)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          <div className="flex gap-3 pt-2 justify-end">
            <button type="button" onClick={onClose}
                    className="px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-canvas2">
              {tUi('EMP_SHARES_CANCEL')}
            </button>
            <button type="submit" disabled={!file || busy}
                    className="px-4 py-2 text-sm bg-violet-600 text-white rounded-lg hover:bg-violet-700
                               disabled:opacity-50 disabled:cursor-not-allowed">
              {tUi('OA_EMP_MASTER_IMPORT_SUBMIT_BTN')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
