import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plug, ToggleLeft, ToggleRight, AlertCircle, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

interface ConnectorDef {
  connector_definition_id: string
  connector_key: string
  display_name: string
  auth_method: string
  supported_modes: string[]
  docs_url?: string
  is_active: boolean
}

function AuthBadge({ method }: { method: string }) {
  const color: Record<string, string> = {
    OAUTH2:  'bg-indigo-50 text-indigo-700 border-indigo-200',
    API_KEY: 'bg-amber-50 text-amber-700 border-amber-200',
    WEBHOOK: 'bg-teal-50 text-teal-700 border-teal-200',
    SFTP:    'bg-slate-50 text-slate-600 border-slate-200',
  }
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${color[method] ?? 'bg-slate-50 text-slate-600 border-slate-200'}`}>
      {method}
    </span>
  )
}

export function HRMSCatalogue() {
  const qc = useQueryClient()

  const { data, isLoading, isError } = useQuery<{ items: ConnectorDef[] }>({
    queryKey: ['pa-hrms-definitions'],
    queryFn:  () => api.get('/v1/admin/hrms/definitions').then(r => r.data),
    staleTime: 60_000,
  })

  const activateMut = useMutation({
    mutationFn: (id: string) => api.patch(`/v1/admin/hrms/definitions/${id}/activate`).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['pa-hrms-definitions'] }),
  })

  const deactivateMut = useMutation({
    mutationFn: (id: string) => api.patch(`/v1/admin/hrms/definitions/${id}/deactivate`).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['pa-hrms-definitions'] }),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48 text-slate-400">
        <Loader2 className="animate-spin mr-2" size={18} />
        {tUi('HRMS_LOADING_CONNECTORS')}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 text-red-600 bg-red-50 rounded-xl p-4">
        <AlertCircle size={16} />
        {tUi('PA_HRMS_CAT_LOAD_FAILED')}
      </div>
    )
  }

  const items = data?.items ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">{tUi('PA_HRMS_CAT_TITLE')}</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {tUi('PA_HRMS_CAT_SUB')}
          </p>
        </div>
        <span className="text-xs text-slate-500">{tUi('PA_HRMS_CAT_COUNT', { n: items.length })}</span>
      </div>

      {items.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <Plug size={32} className="mx-auto mb-3 opacity-40" />
          <p className="text-sm">{tUi('PA_HRMS_CAT_NONE')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {items.map(def => (
            <div
              key={def.connector_definition_id}
              className={`bg-white rounded-xl border shadow-sm p-5 flex flex-col gap-3 ${
                def.is_active ? 'border-slate-200' : 'border-slate-100 opacity-60'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold text-slate-800 text-sm">{def.display_name}</p>
                  <p className="text-xs text-slate-400 font-mono">{def.connector_key}</p>
                </div>
                <AuthBadge method={def.auth_method} />
              </div>

              <div className="flex flex-wrap gap-1">
                {def.supported_modes.map(m => (
                  <span key={m} className="text-xs bg-slate-50 text-slate-500 border border-slate-200 rounded px-1.5 py-0.5">
                    {m}
                  </span>
                ))}
              </div>

              <div className="mt-auto flex items-center justify-between pt-2 border-t border-slate-100">
                {def.docs_url && (
                  <a
                    href={def.docs_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-indigo-600 hover:underline"
                  >
                    {tUi('PA_HRMS_CAT_DOCS_LINK')}
                  </a>
                )}
                <button
                  onClick={() =>
                    def.is_active
                      ? deactivateMut.mutate(def.connector_definition_id)
                      : activateMut.mutate(def.connector_definition_id)
                  }
                  disabled={activateMut.isPending || deactivateMut.isPending}
                  className="ml-auto flex items-center gap-1 text-xs text-slate-600 hover:text-indigo-600 disabled:opacity-50"
                >
                  {def.is_active ? (
                    <><ToggleRight size={16} className="text-indigo-500" /> {tUi('EMP_CAREER_ACTIVE')}</>
                  ) : (
                    <><ToggleLeft size={16} /> {tUi('PA_HRMS_CAT_INACTIVE')}</>
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
