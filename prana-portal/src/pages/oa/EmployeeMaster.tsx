import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Upload, UserPlus } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDate } from '@/lib/utils'

export function EmployeeMaster() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const limit = 20

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-slate-800">Employee Master</h1>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 px-4 py-2 border border-slate-200
                             rounded-lg text-sm font-medium text-slate-600 hover:bg-canvas2">
            <Upload size={14}/> Bulk upload CSV
          </button>
          <button className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white
                             rounded-lg text-sm font-medium hover:bg-violet-700">
            <UserPlus size={14}/> Add employee
          </button>
        </div>
      </div>

      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(0) }}
               placeholder="Search by name, emp ID, or department…"
               className="w-full pl-9 pr-4 py-2.5 border border-slate-200 rounded-lg text-sm
                          focus:outline-none focus:ring-2 focus:ring-violet-500" />
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-canvas2 text-slate-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-5 py-3 font-medium">Name</th>
              <th className="text-left px-5 py-3 font-medium">Emp ID</th>
              <th className="text-left px-5 py-3 font-medium">Department</th>
              <th className="text-left px-5 py-3 font-medium">Designation</th>
              <th className="text-left px-5 py-3 font-medium">DOJ</th>
              <th className="text-left px-5 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading && (
              <tr><td colSpan={6} className="px-5 py-8 text-center text-slate-400">Loading…</td></tr>
            )}
            {!isLoading && data?.employees?.length === 0 && (
              <tr><td colSpan={6} className="px-5 py-8 text-center text-slate-400">No employees found.</td></tr>
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
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        {(data?.count ?? 0) > limit && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100">
            <span className="text-xs text-slate-400">
              Showing {page * limit + 1}–{Math.min((page + 1) * limit, data?.count ?? 0)} of {data?.count}
            </span>
            <div className="flex gap-2">
              <button onClick={() => setPage(p => p - 1)} disabled={page === 0}
                      className="text-xs px-3 py-1 border border-slate-200 rounded disabled:opacity-40
                                 hover:bg-canvas2">← Prev</button>
              <button onClick={() => setPage(p => p + 1)}
                      disabled={(page + 1) * limit >= (data?.count ?? 0)}
                      className="text-xs px-3 py-1 border border-slate-200 rounded disabled:opacity-40
                                 hover:bg-canvas2">Next →</button>
            </div>
          </div>
        )}
      </div>
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
