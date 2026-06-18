import { useQuery } from '@tanstack/react-query'
import { BookOpen, AlertTriangle, CheckCircle, ChevronRight } from 'lucide-react'
import { api } from '@/lib/api'

const SEVERITY_STYLE: Record<string, string> = {
  LOW:    'bg-emerald-50 text-emerald-700 border-emerald-200',
  MEDIUM: 'bg-amber-50  text-amber-700  border-amber-200',
  HIGH:   'bg-red-50    text-red-700    border-red-200',
}

const RISK_ICON: Record<string, JSX.Element> = {
  LOW:    <CheckCircle size={14} className="text-emerald-500" />,
  MEDIUM: <AlertTriangle size={14} className="text-amber-500" />,
  HIGH:   <AlertTriangle size={14} className="text-red-500" />,
}

export function StatutoryCompliance() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['chro-statutory-coverage'],
    queryFn: () => api.get('/v1/chro/statutory-coverage').then(r => r.data),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Statutory Compliance Coverage</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Per-Act document coverage — auditable by Labour Inspector, TDS Auditor, EPFO Officer, Internal CA
          </p>
        </div>
        {data?.overall_risk && (
          <span className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full border ${SEVERITY_STYLE[data.overall_risk]}`}>
            {RISK_ICON[data.overall_risk]}
            {data.overall_risk} overall risk
          </span>
        )}
      </div>

      {/* Summary bar */}
      {data && (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <p className="text-2xl font-bold font-mono text-slate-800">{data.active_employees}</p>
            <p className="text-xs text-slate-500 mt-1">Active employees</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <p className="text-2xl font-bold font-mono text-slate-800">{data.current_fy}</p>
            <p className="text-xs text-slate-500 mt-1">Current financial year</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
            <p className="text-2xl font-bold font-mono text-slate-800">
              {data.acts?.filter((a: any) => a.severity === 'HIGH').length ?? 0}
            </p>
            <p className="text-xs text-red-500 mt-1">Acts with HIGH coverage gap</p>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="space-y-3 animate-pulse">
          {[...Array(4)].map((_, i) => <div key={i} className="h-28 bg-slate-100 rounded-xl" />)}
        </div>
      )}
      {isError && (
        <div className="text-center py-16 text-slate-400">
          <p className="text-sm">Failed to load statutory coverage.</p>
          <button onClick={() => refetch()} className="mt-2 text-xs text-red-600 hover:underline">Retry</button>
        </div>
      )}

      <div className="space-y-4">
        {data?.acts?.map((act: any, i: number) => (
          <div key={i} className={`bg-white rounded-xl border shadow-sm p-6 ${
            act.severity === 'HIGH' ? 'border-red-200' :
            act.severity === 'MEDIUM' ? 'border-amber-200' : 'border-slate-100'
          }`}>
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <BookOpen size={14} className="text-slate-400 shrink-0" />
                  <span className="text-xs font-mono text-slate-500">{act.act}</span>
                  {act.section !== act.act && (
                    <>
                      <ChevronRight size={12} className="text-slate-300" />
                      <span className="text-xs font-medium text-slate-600">{act.section}</span>
                    </>
                  )}
                </div>
                <p className="text-sm font-medium text-slate-800 mt-1">{act.obligation}</p>
                <p className="text-xs text-slate-500 mt-0.5">Period: {act.period}  ·  Deadline: {act.deadline}</p>
              </div>
              <span className={`flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full border shrink-0 ${SEVERITY_STYLE[act.severity]}`}>
                {RISK_ICON[act.severity]}
                {act.severity} risk
              </span>
            </div>

            {/* Coverage bar */}
            <div className="mt-4">
              <div className="flex justify-between text-xs text-slate-500 mb-1.5">
                <span>{act.compliant_employees} of {act.total_employees} employees compliant</span>
                <span className="font-mono font-semibold text-slate-800">{act.coverage_pct}%</span>
              </div>
              <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    act.coverage_pct >= 90 ? 'bg-emerald-500' :
                    act.coverage_pct >= 70 ? 'bg-amber-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${act.coverage_pct}%` }}
                />
              </div>
              {act.gap_count > 0 && (
                <p className="text-xs text-slate-500 mt-1.5">
                  <span className={`font-semibold ${act.severity === 'HIGH' ? 'text-red-600' : 'text-amber-600'}`}>
                    {act.gap_count} employees missing
                  </span>
                  {' '}— push documents via HRMS or Portal upload to close gap
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      {data?.as_of && (
        <p className="text-xs text-slate-400 text-right">
          As of {new Date(data.as_of).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST
        </p>
      )}
    </div>
  )
}
