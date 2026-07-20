import { useQuery } from '@tanstack/react-query'
import { Activity, RefreshCw, ExternalLink } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

const STAGES = ['QUEUED','ENCRYPTING','SCANNING','EXTRACTING','RESOLVING','ROUTED','EXCEPTION'] as const

function getStageLabels(): Record<string, string> {
  return {
    QUEUED:      tUi('PA_PIPELINE_STAGE_QUEUED'),
    ENCRYPTING:  tUi('PA_PIPELINE_STAGE_ENCRYPTING'),
    SCANNING:    tUi('PA_PIPELINE_STAGE_SCANNING'),
    EXTRACTING:  tUi('PA_PIPELINE_STAGE_EXTRACTING'),
    RESOLVING:   tUi('PA_PIPELINE_STAGE_RESOLVING'),
    ROUTED:      tUi('PA_PIPELINE_STAGE_ROUTED'),
    EXCEPTION:   tUi('PA_PIPELINE_STAGE_EXCEPTION'),
  }
}

export function PipelineHealth() {
  const navigate = useNavigate()
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['pa-pipeline'],
    queryFn: () => api.get('/admin/pipeline-health').then(r => r.data),
    refetchInterval: 30_000,
  })
  const STAGE_LABEL = getStageLabels()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">{tUi('PA_PIPELINE_TITLE')}</h1>
          <p className="text-xs text-slate-400 mt-0.5">{tUi('PA_PIPELINE_SUB')}</p>
        </div>
        <button onClick={() => refetch()} className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800">
          <RefreshCw size={12}/> {tUi('CISO_NOTIF_LOG_REFRESH')}
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {STAGES.map(stage => {
          const count = data?.counts?.[stage] ?? 0
          const isError = stage === 'EXCEPTION'
          const isSuccess = stage === 'ROUTED'
          return (
            <button
              key={stage}
              onClick={() => stage === 'EXCEPTION' ? navigate('/admin/exceptions') : undefined}
              className={`stat-card text-left w-full transition-all ${
                isError && count > 0
                  ? 'stat-card-red cursor-pointer hover:shadow-md hover:scale-[1.02]'
                  : isError
                  ? 'stat-card-red cursor-default'
                  : isSuccess
                  ? 'border-emerald-100 cursor-default'
                  : 'cursor-default'
              }`}
            >
              <p className={`text-xl font-bold font-mono ${
                isError && count > 0 ? 'text-red-600' :
                isSuccess ? 'text-emerald-600' : 'text-slate-800'
              }`}>{isLoading ? '—' : count}</p>
              <div className="flex items-center justify-between mt-1">
                <p className="text-xs text-slate-500">{STAGE_LABEL[stage]}</p>
                {isError && count > 0 && <ExternalLink size={11} className="text-red-400" />}
              </div>
            </button>
          )
        })}
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
          <Activity size={14} className="text-violet-500 animate-pulse" />
          <h2 className="font-medium text-slate-800">{tUi('PA_PIPELINE_LATENCY_TITLE')}</h2>
          <span className="ml-auto text-xs text-slate-400">{tUi('PA_PIPELINE_LATENCY_NOTE')}</span>
        </div>
        <div className="divide-y divide-slate-50">
          {STAGES.filter(s => !['ROUTED','EXCEPTION'].includes(s)).map(stage => (
            <div key={stage} className="px-5 py-3 flex items-center gap-4">
              <span className="font-mono text-xs text-slate-500 w-28">{stage}</span>
              <div className="flex-1 grid grid-cols-2 gap-4">
                <span className="text-sm font-mono text-slate-700">
                  p50: <span className="font-bold">{data?.latency?.[stage]?.p50 ?? '—'}{data?.latency?.[stage]?.p50 ? 's' : ''}</span>
                </span>
                <span className="text-sm font-mono text-slate-700">
                  p95: <span className="font-bold">{data?.latency?.[stage]?.p95 ?? '—'}{data?.latency?.[stage]?.p95 ? 's' : ''}</span>
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 text-xs text-amber-700">
        <strong>{tUi('PA_PIPELINE_ABOUT_BOLD')}</strong> {tUi('PA_PIPELINE_ABOUT_BODY')}
      </div>
    </div>
  )
}
