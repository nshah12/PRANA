import { useQuery } from '@tanstack/react-query'
import { Upload, AlertTriangle, ShieldCheck, FileCheck } from 'lucide-react'
import { api } from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import { fmtRelative } from '@/lib/utils'

export function Dashboard() {
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'oa_admin'

  const { data: stats, isLoading: statsLoading, isError: statsError, refetch: refetchStats } = useQuery({
    queryKey: ['oa-dashboard-stats'],
    queryFn: () => api.get('/v1/ingest/stats').then(r => r.data),
  })

  const { data: recent, isLoading: recentLoading } = useQuery({
    queryKey: ['recent-batches'],
    queryFn: () => api.get('/v1/ingest/documents?limit=8').then(r => r.data),
  })

  const { data: exceptions, isLoading: exceptionsLoading } = useQuery({
    queryKey: ['exceptions-summary'],
    queryFn: () => api.get('/v1/org/exceptions').then(r => r.data?.exceptions ?? r.data),
  })

  const isLoading = statsLoading || recentLoading || exceptionsLoading
  if (isLoading) return (
    <div className="space-y-6 animate-pulse">
      <div className="h-6 w-32 bg-slate-200 rounded" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-slate-100 rounded-xl" />)}
      </div>
      <div className="h-64 bg-slate-100 rounded-xl" />
    </div>
  )
  if (statsError) return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-400">
      <p className="text-sm">Failed to load dashboard data.</p>
      <button onClick={() => refetchStats()} className="mt-3 text-xs text-indigo-600 hover:underline">Retry</button>
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-0.5">{user?.tenantName}</p>
      </div>

      {/* Elevation callout for operators */}
      {!isAdmin && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-start gap-3">
          <ShieldCheck size={18} className="text-emerald-600 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-emerald-800">Need to view documents?</p>
            <p className="text-xs text-emerald-600 mt-0.5">Request elevation from an OA-Admin to unlock document viewing for up to 8 hours.</p>
            <a href="/org/elevation"
               className="inline-block mt-2 text-xs font-medium text-emerald-700 hover:underline">
              Request elevation →
            </a>
          </div>
        </div>
      )}

      {/* Exception banner for admins */}
      {isAdmin && exceptions?.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle size={18} className="text-red-600 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-800">
              {exceptions.length} document{exceptions.length > 1 ? 's' : ''} need manual resolution
            </p>
            <a href="/org/exceptions"
               className="inline-block mt-1 text-xs font-medium text-red-700 hover:underline">
              View exception queue →
            </a>
          </div>
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Documents pushed" value={stats?.documents_pushed ?? '—'} color="sky"     icon={<FileCheck size={18}/>} />
        <StatCard label="Pending pipeline" value={stats?.pending_pipeline ?? '—'} color="amber"   icon={<Upload size={18}/>} />
        <StatCard label="Open exceptions"  value={stats?.open_exceptions ?? '—'} color="red"      icon={<AlertTriangle size={18}/>} />
        <StatCard label="Employees"        value={stats?.employees ?? '—'}        color="emerald"  icon={<ShieldCheck size={18}/>} />
      </div>

      {/* Batch activity feed */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <h2 className="font-medium text-slate-800">Recent uploads</h2>
          <a href="/org/upload"
             className="text-xs font-medium text-violet-600 hover:underline">Upload documents</a>
        </div>
        <div className="divide-y divide-slate-50">
          {recent?.documents?.length === 0 && (
            <p className="px-5 py-8 text-sm text-slate-400 text-center">No documents uploaded yet.</p>
          )}
          {recent?.documents?.map((doc: any) => (
            <div key={doc.document_id} className="px-5 py-3 flex items-center gap-4">
              <DocTypeIcon type={doc.doc_type} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-700 truncate">{doc.doc_type.replace(/_/g, ' ')}</p>
                <p className="text-xs text-slate-400 font-mono">{doc.doc_period ?? '—'}</p>
              </div>
              <PipelineStatusBadge status={doc.pipeline_status} />
              <span className="text-xs text-slate-400 whitespace-nowrap">{fmtRelative(doc.pushed_at)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, color, icon }: { label: string; value: any; color: string; icon: React.ReactNode }) {
  const borderMap: Record<string, string> = {
    sky: 'border-t-role-emp', amber: 'border-t-role-pa',
    red: 'border-t-role-ciso', emerald: 'border-t-role-oaop',
  }
  return (
    <div className={`stat-card border-t-4 ${borderMap[color] ?? ''}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-slate-400">{icon}</span>
      </div>
      <p className="text-2xl font-bold text-slate-800 font-mono">{value}</p>
      <p className="text-xs text-slate-500 mt-1">{label}</p>
    </div>
  )
}

function DocTypeIcon({ type }: { type: string }) {
  const map: Record<string, string> = {
    SALARY_SLIP: 'bg-emerald-500', FORM_16: 'bg-sky-500',
    OFFER_LETTER: 'bg-violet-500', APPOINTMENT_LETTER: 'bg-violet-500',
    EXPERIENCE_LETTER: 'bg-amber-500', RELIEVING_LETTER: 'bg-red-500',
  }
  const abbr = type.split('_').map(w => w[0]).join('').slice(0, 2)
  return (
    <div className={`doc-icon ${map[type] ?? 'bg-slate-400'}`}>{abbr}</div>
  )
}

export function PipelineStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    QUEUED: 'badge-muted', ENCRYPTING: 'badge-sky', SCANNING: 'badge-sky',
    EXTRACTING: 'badge-sky', RESOLVING: 'badge-amber',
    ROUTED: 'badge-emerald', EXCEPTION: 'badge-red', QUARANTINED: 'badge-red',
  }
  return <span className={`badge ${map[status] ?? 'badge-muted'}`}>{status}</span>
}
