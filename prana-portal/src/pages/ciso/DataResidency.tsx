import { useQuery } from '@tanstack/react-query'
import { Globe, CheckCircle, AlertTriangle } from 'lucide-react'
import { api } from '@/lib/api'

export function DataResidency() {
  const { data } = useQuery({
    queryKey: ['ciso-residency'],
    queryFn: () => api.get('/v1/ciso/data-residency').then(r => r.data),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold text-slate-800">Data Residency</h1>
        <Globe size={18} className="text-sky-500" />
      </div>

      {/* Region summary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {(data?.regions ?? [
          { region: 'ap-south-1', name: 'Mumbai (Primary)', role: 'PRIMARY', status: 'ACTIVE', doc_count: data?.primary_doc_count },
          { region: 'ap-south-2', name: 'Hyderabad (DR)',   role: 'DR',      status: 'ACTIVE', doc_count: data?.dr_doc_count },
        ]).map((r: any) => (
          <div key={r.region} className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
            <div className="flex items-center gap-3 mb-4">
              {r.status === 'ACTIVE'
                ? <CheckCircle size={18} className="text-emerald-500" />
                : <AlertTriangle size={18} className="text-amber-500" />}
              <div>
                <p className="font-medium text-slate-800">{r.name}</p>
                <p className="text-xs font-mono text-slate-400">{r.region}</p>
              </div>
              <span className={`ml-auto text-xs font-medium px-2 py-0.5 rounded-full ${
                r.role === 'PRIMARY' ? 'bg-indigo-50 text-indigo-700' : 'bg-slate-100 text-slate-600'
              }`}>{r.role}</span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-xs text-slate-400">Documents</p>
                <p className="font-mono text-slate-700 mt-0.5">{r.doc_count ?? '—'}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400">Status</p>
                <p className="text-slate-700 mt-0.5">{r.status}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Storage breakdown */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <h2 className="font-medium text-slate-800 mb-4">Storage breakdown</h2>
        <div className="space-y-3">
          {[
            { label: 'YugabyteDB (encrypted at rest)', region: 'ap-south-1 + ap-south-2', status: 'Dual-region replication active' },
            { label: 'S3 document bucket',             region: 'ap-south-1',              status: data?.s3_bucket ?? 'prana-documents-prod' },
            { label: 'S3 staging bucket',              region: 'ap-south-1',              status: data?.s3_staging_bucket ?? 'prana-staging-prod' },
            { label: 'Audit cold storage (Iceberg)',   region: 'ap-south-1',              status: '7-year retention' },
          ].map(row => (
            <div key={row.label} className="flex items-start gap-4 py-2 border-b border-slate-50 last:border-0">
              <CheckCircle size={14} className="text-emerald-500 mt-0.5 shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-medium text-slate-700">{row.label}</p>
                <p className="text-xs text-slate-400 mt-0.5">{row.region} · {row.status}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-sky-50 border border-sky-100 rounded-xl p-4 text-xs text-sky-700">
        All PRANA data stays within AWS India regions (ap-south-1, ap-south-2). No cross-border data transfers.
        Encryption at rest: AES-256 (YugabyteDB), SSE-S3 (S3). KMS: ap-south-1 customer-managed CMKs.
      </div>
    </div>
  )
}
