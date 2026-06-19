import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { api } from '@/lib/api'

export function PayrollIntelligence() {
  const { data } = useQuery({
    queryKey: ['cfo-payroll'],
    queryFn: () => api.get('/cfo/payroll').then(r => r.data),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Payroll Intelligence</h1>
        <p className="text-xs text-slate-400 mt-0.5 font-mono">
          Cohort min 30 employees · Individual figures never shown
        </p>
      </div>

      {/* 6-month trend */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">6-month payroll trend</h2>
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
        <h2 className="font-medium text-slate-800 mb-4">Salary band distribution</h2>
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
          <p className="text-sm font-medium text-red-700">Integrity flags</p>
          {data.integrity_flags.map((f: string, i: number) => (
            <p key={i} className="text-xs text-red-600">• {f}</p>
          ))}
        </div>
      )}
    </div>
  )
}
