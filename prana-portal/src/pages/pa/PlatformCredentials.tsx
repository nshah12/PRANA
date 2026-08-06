/**
 * PlatformCredentials (PA) — one screen for every paid external-service
 * credential PRANA holds, not just Communication Hub vendors. Merges two
 * backends into one list:
 *   - GET /admin/communications/vendor-credentials (smtp/exotel/msg91/waba/ozonetel —
 *     services/communication_settings_service.py)
 *   - GET /admin/platform-credentials (qdrant, and any future non-channel
 *     paid service — services/platform_credential_service.py)
 * Same KMS-encrypted-at-rest, write-only-rotation, Immudb-audited model for
 * both. Deliberately excludes AWS-family services (S3/KMS/Textract/SES) —
 * those default to IAM roles in production; see
 * services/platform_credential_service.py's module docstring for why a web
 * form for static AWS keys isn't offered here.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Pencil, ShieldCheck, ShieldOff } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

type CredentialStatus = { configured: boolean; source: string }

const SOURCES: Array<{
  queryKey: string
  statusUrl: string
  patchUrl: (vendor: string) => string
}> = [
  {
    queryKey: 'pa-comm-vendor-credentials',
    statusUrl: '/admin/communications/vendor-credentials',
    patchUrl: vendor => `/admin/communications/vendor-credentials/${vendor}`,
  },
  {
    queryKey: 'pa-platform-credentials',
    statusUrl: '/admin/platform-credentials',
    patchUrl: vendor => `/admin/platform-credentials/${vendor}`,
  },
]

export function PlatformCredentials() {
  const qc = useQueryClient()
  const [editField, setEditField] = useState<string | null>(null)   // `${vendor}:${field}`
  const [value, setValue] = useState('')

  const results = SOURCES.map(src => useQuery({
    queryKey: [src.queryKey],
    queryFn: () => api.get(src.statusUrl).then(r => r.data),
  }))

  const isLoading = results.some(r => r.isLoading)
  const isError = results.some(r => r.isError)

  // Merge both sources into one { vendor -> { status, fields, patchUrl } } map.
  const rows: Array<{ vendor: string; status: CredentialStatus; fields: string[]; patchUrl: (v: string) => string }> = []
  results.forEach((r, i) => {
    const vendors: Record<string, CredentialStatus> = r.data?.vendors ?? {}
    const editableFields: Record<string, string[]> = r.data?.editable_fields ?? {}
    Object.entries(vendors).forEach(([vendor, status]) => {
      rows.push({ vendor, status, fields: editableFields[vendor] ?? [], patchUrl: SOURCES[i].patchUrl })
    })
  })

  const update = useMutation({
    mutationFn: ({ vendor, fieldName, patchUrl }: { vendor: string; fieldName: string; patchUrl: (v: string) => string }) =>
      api.patch(patchUrl(vendor), { field_name: fieldName, value }),
    onSuccess: () => {
      SOURCES.forEach(src => qc.invalidateQueries({ queryKey: [src.queryKey] }))
      setEditField(null)
      setValue('')
    },
  })

  function startEdit(vendor: string, field: string) {
    setEditField(`${vendor}:${field}`)
    setValue('')
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
          <KeyRound size={20} className="text-indigo-500" />
          {tUi('PLATFORM_CREDENTIALS_TITLE')}
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">{tUi('PLATFORM_CREDENTIALS_SUB')}</p>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => <div key={i} className="h-12 bg-slate-100 rounded-xl animate-pulse" />)}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <p className="text-sm">{tUi('PLATFORM_CREDENTIALS_LOAD_FAILED')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-slate-400">{tUi('COMM_CREDENTIALS_HINT')}</p>
          <div className="space-y-2">
            {rows.map(({ vendor, status, fields, patchUrl }) => (
              <div key={vendor} className="bg-white border border-slate-200 rounded-xl p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-slate-600">{vendor}</span>
                  <div className="flex items-center gap-2">
                    {status.configured && (
                      <span className="text-[10px] text-slate-400">
                        {status.source === 'db' ? tUi('COMM_CRED_SOURCE_DB') : tUi('COMM_CRED_SOURCE_ENV')}
                      </span>
                    )}
                    {status.configured ? (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 flex items-center gap-1">
                        <ShieldCheck size={12} /> {tUi('COMM_CONFIGURED_BADGE')}
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-400 flex items-center gap-1">
                        <ShieldOff size={12} /> {tUi('COMM_NOT_CONFIGURED_BADGE')}
                      </span>
                    )}
                  </div>
                </div>

                {fields.length > 0 && (
                  <div className="space-y-1.5 pt-2 border-t border-slate-100">
                    {fields.map(field => (
                      <div key={field} className="flex items-center gap-2">
                        <span className="text-[11px] font-mono text-slate-400 w-48 shrink-0 truncate">{field}</span>
                        {editField === `${vendor}:${field}` ? (
                          <>
                            <input
                              type="password"
                              autoComplete="off"
                              aria-label={field}
                              value={value}
                              onChange={e => setValue(e.target.value)}
                              placeholder={tUi('COMM_CRED_VALUE_PLACEHOLDER')}
                              className="flex-1 text-xs border border-slate-200 rounded-lg px-2 py-1"
                            />
                            <button
                              onClick={() => update.mutate({ vendor, fieldName: field, patchUrl })}
                              disabled={!value || update.isPending}
                              className="text-xs px-2 py-1 bg-indigo-600 text-white rounded-lg disabled:opacity-50 shrink-0">
                              {update.isPending ? '…' : tUi('PA_POLICY_SAVE')}
                            </button>
                            <button
                              onClick={() => { setEditField(null); setValue('') }}
                              className="text-xs px-2 py-1 border border-slate-200 rounded-lg text-slate-500 shrink-0">
                              {tUi('CISO_SEC_INC_CANCEL')}
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => startEdit(vendor, field)}
                            className="text-xs px-2 py-1 border border-slate-200 rounded-lg text-slate-500 hover:bg-slate-50 flex items-center gap-1 shrink-0">
                            <Pencil size={10} /> {tUi('COMM_CRED_SET_BUTTON')}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
