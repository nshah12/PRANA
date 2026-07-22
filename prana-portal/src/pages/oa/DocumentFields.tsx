/**
 * OA-Admin — Document Field Manifest editor.
 *
 * Lets an OA-Admin review a doc type's extraction fields (required + identity +
 * optional) and mark which ones are safe (non-monetary) metadata. Anything not
 * marked safe is stripped before being written to document.extracted_fields —
 * see prana-ai/pipeline/stage06_route.py's _SAFE_METADATA_FIELDS, unioned with
 * this manifest's safe_fields. A tenant-custom field the OA-Admin never marks
 * safe is simply dropped, never leaked (fail-closed default).
 *
 * API: GET /v1/manifests            → { items: [manifest, ...] } (doc types with a manifest)
 *      PUT /v1/manifests/{doc_type} → full ManifestUpsertRequest body (creates/updates
 *          a tenant-level override — OA-Admin only; OA-Operator can view but not save)
 */
import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ShieldCheck, CheckCircle, Save, Info, FileStack } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi, tError } from '@/i18n'
import { useAuthStore } from '@/store/auth'

interface ManifestItem {
  manifest_id: string
  doc_type: string
  required_fields: string[]
  identity_fields: string[]
  optional_fields: string[]
  classification_signals: string[][]
  signal_weights: number[]
  confidence_threshold: number
  supported_formats: string[]
  safe_fields: string[]
  is_active: boolean
  is_tenant_override?: boolean
}

function allFieldsOf(m: ManifestItem): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const f of [...m.required_fields, ...m.identity_fields, ...m.optional_fields]) {
    if (!seen.has(f)) {
      seen.add(f)
      out.push(f)
    }
  }
  return out
}

export function DocumentFields() {
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'oa_admin'
  const qc = useQueryClient()

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['oa-manifests'],
    queryFn: () => api.get('/v1/manifests').then(r => r.data),
  })

  const items: ManifestItem[] = data?.items ?? []
  const [selected, setSelected] = useState<string | null>(null)
  const [safeSet, setSafeSet] = useState<Set<string>>(new Set())
  const [saved, setSaved] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  useEffect(() => {
    if (!selected && items.length > 0) setSelected(items[0].doc_type)
  }, [items, selected])

  const current = items.find(m => m.doc_type === selected) || null

  useEffect(() => {
    if (current) {
      setSafeSet(new Set(current.safe_fields))
      setSaved(false)
      setErrorMsg(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.doc_type])

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!current) return Promise.reject(new Error('no doc type selected'))
      return api.put(`/v1/manifests/${current.doc_type}`, {
        required_fields: current.required_fields,
        identity_fields: current.identity_fields,
        optional_fields: current.optional_fields,
        classification_signals: current.classification_signals,
        signal_weights: current.signal_weights,
        confidence_threshold: current.confidence_threshold,
        supported_formats: current.supported_formats,
        is_active: current.is_active,
        safe_fields: [...safeSet],
      })
    },
    onSuccess: () => {
      setSaved(true)
      setErrorMsg(null)
      qc.invalidateQueries({ queryKey: ['oa-manifests'] })
      setTimeout(() => setSaved(false), 3000)
    },
    onError: (e: any) => {
      setErrorMsg(tError(e?.response?.data?.detail))
    },
  })

  function toggle(field: string) {
    if (!isAdmin) return
    setSafeSet(prev => {
      const next = new Set(prev)
      if (next.has(field)) next.delete(field)
      else next.add(field)
      return next
    })
    setSaved(false)
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(3)].map((_, i) => <div key={i} className="h-16 bg-slate-100 rounded-xl animate-pulse" />)}
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex flex-col items-center py-16 text-slate-400">
        <p className="text-sm">{tUi('OA_DOC_FIELDS_LOAD_FAILED')}</p>
        <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">
          {tUi('CFO_ATTRITION_RETRY')}
        </button>
      </div>
    )
  }
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center py-16 text-slate-400">
        <FileStack size={40} className="text-slate-300 mb-3" />
        <p className="font-medium text-slate-600">{tUi('OA_DOC_FIELDS_EMPTY')}</p>
      </div>
    )
  }

  const fields = current ? allFieldsOf(current) : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
          <ShieldCheck size={20} className="text-indigo-500" /> {tUi('OA_DOC_FIELDS_TITLE')}
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">{tUi('OA_DOC_FIELDS_SUB')}</p>
      </div>

      <div className="flex gap-6 items-start">
        <div className="w-56 shrink-0 space-y-1">
          {items.map(m => (
            <button
              key={m.doc_type}
              onClick={() => setSelected(m.doc_type)}
              className={`w-full text-left text-sm px-3 py-2 rounded-lg transition-colors ${
                selected === m.doc_type ? 'bg-indigo-50 text-indigo-700 font-medium' : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              {m.doc_type}
              {m.is_tenant_override && (
                <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-700">
                  {tUi('OA_DOC_FIELDS_OVERRIDE_BADGE')}
                </span>
              )}
            </button>
          ))}
        </div>

        {current && (
          <div className="flex-1 bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-4">
            <div className="flex gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5">
              <Info size={13} className="text-slate-400 mt-0.5 shrink-0" />
              <p className="text-xs text-slate-500 leading-4">{tUi('OA_DOC_FIELDS_SAFE_EXPLAINER')}</p>
            </div>

            <div className="divide-y divide-slate-100">
              {fields.map(field => {
                const checked = safeSet.has(field)
                return (
                  <label
                    key={field}
                    className={`flex items-center justify-between py-3 select-none ${isAdmin ? 'cursor-pointer' : 'cursor-not-allowed opacity-70'}`}
                    onClick={() => toggle(field)}
                  >
                    <span className="text-sm font-mono text-slate-700">{field}</span>
                    <div className={`w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 transition-colors
                      ${checked ? 'border-emerald-600 bg-emerald-600' : 'border-slate-300 bg-white'}`}>
                      {checked && (
                        <svg viewBox="0 0 10 8" className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" strokeWidth={2}>
                          <path d="M1 4l3 3 5-6" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </div>
                  </label>
                )
              })}
              {fields.length === 0 && (
                <p className="text-xs text-slate-400 py-3">{tUi('OA_DOC_FIELDS_NO_FIELDS')}</p>
              )}
            </div>

            {errorMsg && (
              <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
                <p className="text-xs text-red-600">{errorMsg}</p>
              </div>
            )}

            {isAdmin && (
              <div className="pt-1">
                <button
                  onClick={() => saveMutation.mutate()}
                  disabled={saveMutation.isPending}
                  className="flex items-center gap-2 px-5 py-2.5 bg-violet-600 text-white
                             rounded-lg text-sm font-medium hover:bg-violet-700 disabled:opacity-40 transition-opacity"
                >
                  {saved
                    ? <><CheckCircle size={14} /> {tUi('OA_ORG_PROFILE_SAVED')}</>
                    : saveMutation.isPending
                      ? tUi('OA_ORG_PROFILE_SAVING')
                      : <><Save size={14} /> {tUi('OA_DOC_FIELDS_SAVE_BTN')}</>
                  }
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
