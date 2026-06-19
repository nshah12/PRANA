import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { Download } from 'lucide-react'
import { api } from '@/lib/api'

export function VaultHealthChro() {
  const { data, isLoading } = useQuery({
    queryKey: ['chro-vault-health'],
    queryFn: () => api.get('/v1/chro/vault-health').then(r => r.data),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Vault Health Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">Organisation-wide document completeness</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 border border-slate-200
                           rounded-lg text-sm font-medium text-slate-600 hover:bg-canvas2">
          <Download size={14}/> Export PDF
        </button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Overall score', value: data?.overall_score ?? '—', unit: '%', color: 'sky' },
          { label: 'Employment proof', value: data?.employment_proof_score ?? '—', unit: '%', color: 'emerald' },
          { label: 'Salary slips', value: data?.salary_slip_score ?? '—', unit: '%', color: 'violet' },
          { label: 'Form-16 history', value: data?.form16_score ?? '—', unit: '%', color: 'amber' },
        ].map(card => (
          <div key={card.label} className={`stat-card stat-card-${card.color}`}>
            <p className="text-2xl font-bold font-mono text-slate-800">
              {card.value}{typeof card.value === 'number' ? card.unit : ''}
            </p>
            <p className="text-xs text-slate-500 mt-1">{card.label}</p>
          </div>
        ))}
      </div>

      {/* Dept breakdown chart */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">Department breakdown</h2>
        {isLoading ? (
          <div className="h-48 flex items-center justify-center text-slate-400 text-sm">Loading…</div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data?.by_department ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
              <XAxis dataKey="department" tick={{ fontSize: 11, fill: '#94A3B8' }} />
              <YAxis tick={{ fontSize: 11, fill: '#94A3B8' }} domain={[0, 100]} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, 'Completeness']} />
              <Bar dataKey="score" fill="#8B5CF6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Gap cards */}
      {data?.gaps?.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-3">
          <h2 className="font-medium text-slate-800">Gaps detected</h2>
          {data.gaps.map((gap: any, i: number) => (
            <div key={i} className="flex items-center justify-between p-4 bg-canvas2 rounded-xl">
              <div>
                <p className="text-sm font-medium text-slate-700">{gap.description}</p>
                <p className="text-xs text-slate-400 mt-0.5">{gap.affected_count} employees affected</p>
              </div>
              <button className="text-xs font-medium text-violet-600 hover:underline">
                Alert OA-Operator
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
