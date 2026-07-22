/**
 * OA-Admin — Go-Live Checklist.
 *
 * Blocking pre-upload readiness gate: effective checklist = platform baseline
 * (PA-owned) ∪ this tenant's own items (OA-Admin-owned). Every required
 * active item must have a completion row before ingest.py's 3 upload
 * entrypoints will accept a document (403 SETUP_CHECKLIST_INCOMPLETE
 * otherwise) — this page is where an OA-Admin clears that gate.
 *
 * API: GET    /v1/org/setup-checklist
 *      POST   /v1/org/setup-checklist/{item_key}/complete
 *      DELETE /v1/org/setup-checklist/{item_key}/complete
 *      POST   /v1/org/setup-checklist            (add own item)
 *      DELETE /v1/org/setup-checklist/{item_key}  (delete own item)
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckSquare, CheckCircle2, Circle, Plus, X, Info } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi, tError } from '@/i18n'
import { useAuthStore } from '@/store/auth'

interface ChecklistItem {
  item_id: string
  is_platform_baseline: boolean
  item_key: string
  title: string
  description: string | null
  is_required: boolean
  completed: boolean
  completed_at: string | null
  notes: string | null
}

export function SetupChecklist() {
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'oa_admin'
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newRequired, setNewRequired] = useState(true)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['setup-checklist'],
    queryFn: () => api.get('/v1/org/setup-checklist').then(r => r.data),
  })

  const items: ChecklistItem[] = data?.items ?? []
  const requiredItems = items.filter(i => i.is_required)
  const allRequiredComplete = requiredItems.length > 0 && requiredItems.every(i => i.completed)

  const toggleMutation = useMutation({
    mutationFn: (item: ChecklistItem) =>
      item.completed
        ? api.delete(`/v1/org/setup-checklist/${item.item_key}/complete`)
        : api.post(`/v1/org/setup-checklist/${item.item_key}/complete`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['setup-checklist'] }),
    onError: (e: any) => setErrorMsg(tError(e?.response?.data?.detail)),
  })

  const addMutation = useMutation({
    mutationFn: () => api.post('/v1/org/setup-checklist', {
      item_key: newKey, title: newTitle, description: newDesc || null, is_required: newRequired,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['setup-checklist'] })
      setShowAdd(false); setNewKey(''); setNewTitle(''); setNewDesc(''); setNewRequired(true)
      setErrorMsg(null)
    },
    onError: (e: any) => setErrorMsg(tError(e?.response?.data?.detail)),
  })

  const deleteMutation = useMutation({
    mutationFn: (itemKey: string) => api.delete(`/v1/org/setup-checklist/${itemKey}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['setup-checklist'] }),
    onError: (e: any) => setErrorMsg(tError(e?.response?.data?.detail)),
  })

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
        <p className="text-sm">{tUi('OA_CHECKLIST_LOAD_FAILED')}</p>
        <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">
          {tUi('CFO_ATTRITION_RETRY')}
        </button>
      </div>
    )
  }
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center py-16 text-slate-400">
        <CheckSquare size={40} className="text-slate-300 mb-3" />
        <p className="font-medium text-slate-600">{tUi('OA_CHECKLIST_EMPTY')}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
          <CheckSquare size={20} className="text-indigo-500" /> {tUi('OA_CHECKLIST_TITLE')}
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">{tUi('OA_CHECKLIST_SUB')}</p>
      </div>

      {allRequiredComplete && (
        <div className="flex gap-2 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3">
          <CheckCircle2 size={16} className="text-emerald-600 mt-0.5 shrink-0" />
          <p className="text-sm text-emerald-700">{tUi('OA_CHECKLIST_ALL_COMPLETE')}</p>
        </div>
      )}

      {errorMsg && (
        <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
          <p className="text-xs text-red-600">{errorMsg}</p>
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm divide-y divide-slate-100">
        {items.map(item => (
          <div key={item.item_id} className="flex items-start gap-3 px-5 py-4">
            <button
              onClick={() => isAdmin && toggleMutation.mutate(item)}
              disabled={!isAdmin || toggleMutation.isPending}
              className={isAdmin ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}
            >
              {item.completed
                ? <CheckCircle2 size={20} className="text-emerald-600" />
                : <Circle size={20} className="text-slate-300" />}
            </button>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium text-slate-800">{item.title}</span>
                {!item.is_required && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">
                    {tUi('OA_CHECKLIST_OPTIONAL_BADGE')}
                  </span>
                )}
                {item.is_platform_baseline ? (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-600">
                    {tUi('OA_CHECKLIST_BASELINE_BADGE')}
                  </span>
                ) : (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-700">
                    {tUi('OA_CHECKLIST_CUSTOM_BADGE')}
                  </span>
                )}
              </div>
              {item.description && (
                <p className="text-xs text-slate-500 mt-0.5">{item.description}</p>
              )}
            </div>
            {isAdmin && !item.is_platform_baseline && (
              <button
                onClick={() => deleteMutation.mutate(item.item_key)}
                className="text-slate-300 hover:text-red-500 shrink-0"
              >
                <X size={14} />
              </button>
            )}
          </div>
        ))}
      </div>

      {isAdmin && (
        <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-5">
          {!showAdd ? (
            <button
              onClick={() => setShowAdd(true)}
              className="flex items-center gap-2 text-sm font-medium text-indigo-600 hover:text-indigo-700"
            >
              <Plus size={14} /> {tUi('OA_CHECKLIST_ADD_ITEM_BTN')}
            </button>
          ) : (
            <div className="space-y-3">
              <div className="flex gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5">
                <Info size={13} className="text-slate-400 mt-0.5 shrink-0" />
                <p className="text-xs text-slate-500 leading-4">{tUi('OA_CHECKLIST_ADD_ITEM_EXPLAINER')}</p>
              </div>
              <input
                value={newKey} onChange={e => setNewKey(e.target.value.toUpperCase())}
                placeholder={tUi('OA_CHECKLIST_KEY_PLACEHOLDER')}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 font-mono"
              />
              <input
                value={newTitle} onChange={e => setNewTitle(e.target.value)}
                placeholder={tUi('OA_CHECKLIST_TITLE_PLACEHOLDER')}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2"
              />
              <textarea
                value={newDesc} onChange={e => setNewDesc(e.target.value)}
                placeholder={tUi('OA_CHECKLIST_DESC_PLACEHOLDER')}
                rows={2}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 resize-none"
              />
              <label className="flex items-center gap-2 text-xs text-slate-500">
                <input type="checkbox" checked={newRequired} onChange={e => setNewRequired(e.target.checked)} />
                {tUi('OA_CHECKLIST_REQUIRED_LABEL')}
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => addMutation.mutate()}
                  disabled={!newKey || !newTitle || addMutation.isPending}
                  className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                >
                  {addMutation.isPending ? '…' : tUi('OA_CHECKLIST_SAVE_ITEM_BTN')}
                </button>
                <button
                  onClick={() => setShowAdd(false)}
                  className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500"
                >
                  {tUi('CISO_SEC_INC_CANCEL')}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
