/**
 * PA — Go-Live Checklist template (platform-baseline items).
 *
 * Manages the checklist every tenant inherits (setup_checklist_item rows
 * with tenant_id IS NULL). A tenant's OA-Admin can add their own items on top
 * of this baseline (oa/SetupChecklist.tsx) but can never edit or remove a
 * baseline item — only PA can, here.
 *
 * API: GET   /admin/setup-checklist
 *      POST  /admin/setup-checklist
 *      PATCH /admin/setup-checklist/{item_id}
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckSquare, CheckCircle, Plus, Pencil, X } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi, tError } from '@/i18n'

interface PlatformChecklistItem {
  item_id: string
  item_key: string
  title: string
  description: string | null
  display_order: number
  is_active: boolean
  is_required: boolean
}

const NEW_ITEM_DEFAULT = { item_key: '', title: '', description: '', is_required: true, display_order: '' }

export function SetupChecklistTemplate() {
  const qc = useQueryClient()
  const [showNew, setShowNew] = useState(false)
  const [newItem, setNewItem] = useState(NEW_ITEM_DEFAULT)
  const [editId, setEditId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<any>({})
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-setup-checklist'],
    queryFn: () => api.get('/admin/setup-checklist').then(r => r.data),
  })

  const items: PlatformChecklistItem[] = data?.items ?? []

  const create = useMutation({
    mutationFn: () => api.post('/admin/setup-checklist', {
      item_key: newItem.item_key.toUpperCase(),
      title: newItem.title,
      description: newItem.description || null,
      is_required: newItem.is_required,
      display_order: newItem.display_order === '' ? 0 : Number(newItem.display_order),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-setup-checklist'] })
      setShowNew(false); setNewItem(NEW_ITEM_DEFAULT); setErrorMsg(null)
    },
    onError: (e: any) => setErrorMsg(tError(e?.response?.data?.detail)),
  })

  const update = useMutation({
    mutationFn: (itemId: string) => api.patch(`/admin/setup-checklist/${itemId}`, {
      title: editForm.title,
      description: editForm.description || null,
      display_order: editForm.display_order === '' ? undefined : Number(editForm.display_order),
      is_required: editForm.is_required,
      is_active: editForm.is_active,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-setup-checklist'] })
      setEditId(null); setErrorMsg(null)
    },
    onError: (e: any) => setErrorMsg(tError(e?.response?.data?.detail)),
  })

  function startEdit(item: PlatformChecklistItem) {
    setEditId(item.item_id)
    setEditForm({
      title: item.title, description: item.description ?? '',
      display_order: item.display_order, is_required: item.is_required, is_active: item.is_active,
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(3)].map((_, i) => <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />)}
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex flex-col items-center py-16 text-slate-400">
        <p className="text-sm">{tUi('PA_CHECKLIST_LOAD_FAILED')}</p>
        <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">
          {tUi('CFO_ATTRITION_RETRY')}
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
            <CheckSquare size={20} className="text-indigo-500" /> {tUi('PA_CHECKLIST_TITLE')}
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">{tUi('PA_CHECKLIST_SUB')}</p>
        </div>
        <button
          onClick={() => setShowNew(v => !v)}
          className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 flex items-center gap-1 shrink-0"
        >
          {showNew ? <X size={12} /> : <Plus size={12} />}
          {showNew ? tUi('CISO_SEC_INC_CANCEL') : tUi('PA_CHECKLIST_ADD_BTN')}
        </button>
      </div>

      {errorMsg && (
        <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
          <p className="text-xs text-red-600">{errorMsg}</p>
        </div>
      )}

      {showNew && (
        <div className="bg-white border border-indigo-200 rounded-xl p-4 space-y-3">
          <input
            value={newItem.item_key} onChange={e => setNewItem({ ...newItem, item_key: e.target.value.toUpperCase() })}
            placeholder={tUi('OA_CHECKLIST_KEY_PLACEHOLDER')}
            className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 font-mono"
          />
          <input
            value={newItem.title} onChange={e => setNewItem({ ...newItem, title: e.target.value })}
            placeholder={tUi('OA_CHECKLIST_TITLE_PLACEHOLDER')}
            className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2"
          />
          <textarea
            value={newItem.description} onChange={e => setNewItem({ ...newItem, description: e.target.value })}
            placeholder={tUi('OA_CHECKLIST_DESC_PLACEHOLDER')} rows={2}
            className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 resize-none"
          />
          <div className="flex items-center gap-4">
            <label className="text-xs text-slate-500 flex items-center gap-1.5">
              <input type="checkbox" checked={newItem.is_required}
                onChange={e => setNewItem({ ...newItem, is_required: e.target.checked })} />
              {tUi('OA_CHECKLIST_REQUIRED_LABEL')}
            </label>
            <label className="text-xs text-slate-500">
              {tUi('PA_POLICY_PRIORITY_LABEL')}
              <input type="number" value={newItem.display_order}
                onChange={e => setNewItem({ ...newItem, display_order: e.target.value })}
                className="ml-2 w-20 text-sm border border-slate-200 rounded-lg px-2 py-1" />
            </label>
          </div>
          <button
            onClick={() => create.mutate()}
            disabled={!newItem.item_key || !newItem.title || create.isPending}
            className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {create.isPending ? '…' : tUi('PA_POLICY_CREATE_RULE')}
          </button>
        </div>
      )}

      {items.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <CheckCircle size={40} className="text-emerald-400 mb-3" />
          <p className="font-medium text-slate-600">{tUi('PA_CHECKLIST_EMPTY')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map(item => (
            <div key={item.item_id} className={`bg-white border rounded-xl p-4 ${item.is_active ? 'border-slate-200' : 'border-slate-100 opacity-60'}`}>
              {editId === item.item_id ? (
                <div className="space-y-3">
                  <input
                    value={editForm.title} onChange={e => setEditForm({ ...editForm, title: e.target.value })}
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2"
                  />
                  <textarea
                    value={editForm.description} onChange={e => setEditForm({ ...editForm, description: e.target.value })}
                    rows={2} className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 resize-none"
                  />
                  <div className="flex items-center gap-4">
                    <label className="text-xs text-slate-500 flex items-center gap-1.5">
                      <input type="checkbox" checked={editForm.is_required}
                        onChange={e => setEditForm({ ...editForm, is_required: e.target.checked })} />
                      {tUi('OA_CHECKLIST_REQUIRED_LABEL')}
                    </label>
                    <label className="text-xs text-slate-500 flex items-center gap-1.5">
                      <input type="checkbox" checked={editForm.is_active}
                        onChange={e => setEditForm({ ...editForm, is_active: e.target.checked })} />
                      {tUi('PA_POLICY_IS_ACTIVE_LABEL')}
                    </label>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => update.mutate(item.item_id)}
                      disabled={update.isPending}
                      className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                      {update.isPending ? '…' : tUi('PA_POLICY_SAVE')}
                    </button>
                    <button onClick={() => setEditId(null)} className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500">
                      {tUi('CISO_SEC_INC_CANCEL')}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-slate-800">{item.title}</span>
                      <span className="text-xs font-mono text-slate-400">{item.item_key}</span>
                      {!item.is_required && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">
                          {tUi('OA_CHECKLIST_OPTIONAL_BADGE')}
                        </span>
                      )}
                      {!item.is_active && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-400">
                          {tUi('PA_POLICY_INACTIVE_BADGE')}
                        </span>
                      )}
                    </div>
                    {item.description && <p className="text-xs text-slate-500">{item.description}</p>}
                  </div>
                  <button
                    onClick={() => startEdit(item)}
                    className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500 hover:bg-slate-50 flex items-center gap-1 shrink-0">
                    <Pencil size={11} /> {tUi('PA_POLICY_EDIT')}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
