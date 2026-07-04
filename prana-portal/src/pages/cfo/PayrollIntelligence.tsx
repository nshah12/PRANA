import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

export function PayrollIntelligence() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['cfo-payroll'],
    queryFn: () => api.get('/v1/cfo/payroll').then(r => r.data),
  })

  const header = (
    <div>
      <h1 className="text-xl font-semibold text-slate-800">{tUi('CFO_PAYROLL_TITLE')}</h1>
      <p className="text-xs text-slate-400 mt-0.5 font-mono">
        {tUi('CFO_PAYROLL_SUB')}
      </p>
    </div>
  )

  if (isLoading) return (
    <div className="space-y-6">
      {header}
      <div className="animate-pulse space-y-4">
        <div className="h-52 bg-slate-100 rounded-xl" />
        <div className="h-44 bg-slate-100 rounded-xl" />
      </div>
    </div>
  )

  if (isError) return (
    <div className="space-y-6">
      {header}
      <div className="flex flex-col items-center justify-center py-20 text-slate-400">
        <p className="text-sm">{tUi('CFO_PAYROLL_LOAD_FAILED')}</p>
        <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">{tUi('CFO_ATTRITION_RETRY')}</button>
      </div>
    </div>
  )

  return (
    <div className="space-y-6">
      {header}

      {/* 6-month trend */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">{tUi('CFO_PAYROLL_TREND_LABEL')}</h2>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data?.trend ?? []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94A3B8' }} />
            <YAxis tick={{ fontSize: 11, fill: '#94A3B8' }} tickFormatter={v => `₹${(v/1e7).toFixed(1)}Cr`} />
            <Tooltip formatter={(v: any) => [`₹${(v/1e7).toFixed(2)} Cr`, 'Payroll']} />
            <Line type="monotone" dataKey="total" stroke="#6366F1" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Band distribution */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">{tUi('CFO_PAYROLL_BAND_DIST_LABEL')}</h2>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data?.band_distribution ?? []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis dataKey="band" tick={{ fontSize: 10, fill: '#94A3B8' }} />
            <YAxis tick={{ fontSize: 11, fill: '#94A3B8' }} />
            <Tooltip />
            <Bar dataKey="count" fill="#6366F1" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Integrity flags */}
      {data?.integrity_flags?.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-5 space-y-2">
          <p className="text-sm font-medium text-red-700">{tUi('CFO_PAYROLL_INTEGRITY_FLAGS')}</p>
          {data.integrity_flags.map((f: string, i: number) => (
            <p key={i} className="text-xs text-red-600">• {f}</p>
          ))}
        </div>
      )}
    </div>
  )
}
