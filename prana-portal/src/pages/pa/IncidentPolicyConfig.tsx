/**
 * IncidentPolicyConfig — PA-facing config for the severity/SLA policy engine.
 * Backed by sla_policy + severity_classification_rule (prana-db/migrations/041,
 * services/severity_policy_service.py). See prana-docs/SEVERITY_SLA_POLICY_DESIGN.md §5.
 * Two tabs: SLA & Auto-Incident (per-severity SLA minutes + auto_create_incident),
 * and Classification Rules (the rule engine every domain — anomaly detection, error
 * observability, health checks — reads its severity/threshold decisions from).
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Clock, CheckCircle, Filter, Plus, Pencil, X } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

const SEV_PILL: Record<string, string> = {
  P0: 'bg-red-100 text-red-700 border border-red-300',
  P1: 'bg-orange-100 text-orange-700 border border-orange-300',
  P2: 'bg-amber-100 text-amber-700 border border-amber-200',
  P3: 'bg-slate-100 text-slate-600 border border-slate-200',
}

const DOMAINS = ['ANOMALY_RULE', 'ERROR_OBSERVABILITY', 'HEALTH_CHECK']

function SlaTab() {
  const qc = useQueryClient()
  const [editSev, setEditSev] = useState<string | null>(null)
  const [slaMinutes, setSlaMinutes] = useState('')
  const [autoCreate, setAutoCreate] = useState(false)
  const [description, setDescription] = useState('')

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-sla-policy'],
    queryFn: () => api.get('/admin/sla-policy').then(r => r.data),
  })

  const update = useMutation({
    mutationFn: (severity: string) =>
      api.patch(`/admin/sla-policy/${severity}`, {
        sla_minutes: slaMinutes ? Number(slaMinutes) : null,
        auto_create_incident: autoCreate,
        description: description || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-sla-policy'] })
      setEditSev(null)
    },
  })

  const policies: any[] = data?.items ?? []

  function startEdit(p: any) {
    setEditSev(p.severity)
    setSlaMinutes(String(p.sla_minutes))
    setAutoCreate(p.auto_create_incident)
    setDescription(p.description ?? '')
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />)}
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex flex-col items-center py-16 text-slate-400">
        <p className="text-sm">{tUi('PA_POLICY_SLA_LOAD_FAILED')}</p>
        <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">
          {tUi('CFO_ATTRITION_RETRY')}
        </button>
      </div>
    )
  }
  if (policies.length === 0) {
    return (
      <div className="flex flex-col items-center py-16 text-slate-400">
        <CheckCircle size={40} className="text-emerald-400 mb-3" />
        <p className="font-medium text-slate-600">{tUi('PA_POLICY_SLA_EMPTY')}</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {policies.map((p: any) => (
        <div key={p.severity} className="bg-white border border-slate-200 rounded-xl p-4">
          {editSev === p.severity ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${SEV_PILL[p.severity] ?? ''}`}>
                  {p.severity}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs text-slate-500">
                  {tUi('PA_POLICY_SLA_MINUTES_LABEL')}
                  <input
                    type="number"
                    min={1}
                    value={slaMinutes}
                    onChange={e => setSlaMinutes(e.target.value)}
                    className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5"
                  />
                </label>
                <label className="text-xs text-slate-500 flex items-center gap-2 mt-5">
                  <input
                    type="checkbox"
                    checked={autoCreate}
                    onChange={e => setAutoCreate(e.target.checked)}
                  />
                  {tUi('PA_POLICY_AUTO_CREATE_LABEL')}
                </label>
              </div>
              <label className="text-xs text-slate-500 block">
                {tUi('PA_POLICY_DESCRIPTION_LABEL')}
                <textarea
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  rows={2}
                  className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5 resize-none"
                />
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => update.mutate(p.severity)}
                  disabled={!slaMinutes || update.isPending}
                  className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                  {update.isPending ? '…' : tUi('PA_POLICY_SAVE')}
                </button>
                <button
                  onClick={() => setEditSev(null)}
                  className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500">
                  {tUi('CISO_SEC_INC_CANCEL')}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0 space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${SEV_PILL[p.severity] ?? ''}`}>
                    {p.severity}
                  </span>
                  <span className="flex items-center gap-1 text-xs text-slate-500">
                    <Clock size={11} /> {p.sla_minutes} {tUi('PA_POLICY_MINUTES_SUFFIX')}
                  </span>
                  {p.auto_create_incident && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                      {tUi('PA_POLICY_AUTO_CREATE_BADGE')}
                    </span>
                  )}
                </div>
                {p.description && <p className="text-xs text-slate-500">{p.description}</p>}
              </div>
              <button
                onClick={() => startEdit(p)}
                className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500 hover:bg-slate-50 flex items-center gap-1 shrink-0">
                <Pencil size={11} /> {tUi('PA_POLICY_EDIT')}
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

const NEW_RULE_DEFAULT = {
  domain: 'ANOMALY_RULE', match_type: 'EXACT', match_value: '',
  occurrence_threshold: '', occurrence_threshold_max: '', window_minutes: '',
  severity: 'P2', priority: '100', description: '',
}

function RulesTab() {
  const qc = useQueryClient()
  const [domain, setDomain] = useState('')
  const [editId, setEditId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<any>({})
  const [showNew, setShowNew] = useState(false)
  const [newForm, setNewForm] = useState<any>(NEW_RULE_DEFAULT)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-severity-rules', domain],
    queryFn: () => api.get(`/admin/severity-rules${domain ? `?domain=${domain}` : ''}`).then(r => r.data),
  })

  const update = useMutation({
    mutationFn: (ruleId: string) =>
      api.patch(`/admin/severity-rules/${ruleId}`, {
        occurrence_threshold: editForm.occurrence_threshold === '' ? null : Number(editForm.occurrence_threshold),
        occurrence_threshold_max: editForm.occurrence_threshold_max === '' ? null : Number(editForm.occurrence_threshold_max),
        window_minutes: editForm.window_minutes === '' ? null : Number(editForm.window_minutes),
        severity: editForm.severity,
        priority: editForm.priority === '' ? null : Number(editForm.priority),
        is_active: editForm.is_active,
        description: editForm.description || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-severity-rules'] })
      setEditId(null)
    },
  })

  const create = useMutation({
    mutationFn: () =>
      api.post('/admin/severity-rules', {
        domain: newForm.domain,
        match_type: newForm.match_type,
        match_value: newForm.match_type === 'DEFAULT' ? null : newForm.match_value,
        occurrence_threshold: newForm.occurrence_threshold === '' ? null : Number(newForm.occurrence_threshold),
        occurrence_threshold_max: newForm.occurrence_threshold_max === '' ? null : Number(newForm.occurrence_threshold_max),
        window_minutes: newForm.window_minutes === '' ? null : Number(newForm.window_minutes),
        severity: newForm.severity,
        priority: Number(newForm.priority || 100),
        description: newForm.description || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-severity-rules'] })
      setShowNew(false)
      setNewForm(NEW_RULE_DEFAULT)
    },
  })

  const rules: any[] = data?.items ?? []

  function startEdit(r: any) {
    setEditId(r.rule_id)
    setEditForm({
      occurrence_threshold: r.occurrence_threshold ?? '',
      occurrence_threshold_max: r.occurrence_threshold_max ?? '',
      window_minutes: r.window_minutes ?? '',
      severity: r.severity,
      priority: r.priority,
      is_active: r.is_active,
      description: r.description ?? '',
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Filter size={14} className="text-slate-400" />
          <select value={domain} onChange={e => setDomain(e.target.value)}
            className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600 bg-white">
            <option value="">{tUi('PA_POLICY_ALL_DOMAINS')}</option>
            {DOMAINS.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <button
          onClick={() => setShowNew(v => !v)}
          className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 flex items-center gap-1">
          {showNew ? <X size={12} /> : <Plus size={12} />}
          {showNew ? tUi('CISO_SEC_INC_CANCEL') : tUi('PA_POLICY_NEW_RULE')}
        </button>
      </div>

      {showNew && (
        <div className="bg-white border border-indigo-200 rounded-xl p-4 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <label className="text-xs text-slate-500">
              {tUi('PA_POLICY_DOMAIN_LABEL')}
              <select value={newForm.domain} onChange={e => setNewForm({ ...newForm, domain: e.target.value })}
                className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5 bg-white">
                {DOMAINS.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
            <label className="text-xs text-slate-500">
              {tUi('PA_POLICY_MATCH_TYPE_LABEL')}
              <select value={newForm.match_type} onChange={e => setNewForm({ ...newForm, match_type: e.target.value })}
                className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5 bg-white">
                {['PREFIX', 'EXACT', 'DEFAULT'].map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
            <label className="text-xs text-slate-500">
              {tUi('PA_POLICY_SEVERITY_LABEL')}
              <select value={newForm.severity} onChange={e => setNewForm({ ...newForm, severity: e.target.value })}
                className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5 bg-white">
                {['P0', 'P1', 'P2', 'P3'].map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
          </div>
          {newForm.match_type !== 'DEFAULT' && (
            <label className="text-xs text-slate-500 block">
              {tUi('PA_POLICY_MATCH_VALUE_LABEL')}
              <input value={newForm.match_value} onChange={e => setNewForm({ ...newForm, match_value: e.target.value })}
                className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5" />
            </label>
          )}
          <div className="grid grid-cols-4 gap-3">
            <label className="text-xs text-slate-500">
              {tUi('PA_POLICY_OCCURRENCE_MIN_LABEL')}
              <input type="number" value={newForm.occurrence_threshold}
                onChange={e => setNewForm({ ...newForm, occurrence_threshold: e.target.value })}
                className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5" />
            </label>
            <label className="text-xs text-slate-500">
              {tUi('PA_POLICY_OCCURRENCE_MAX_LABEL')}
              <input type="number" value={newForm.occurrence_threshold_max}
                onChange={e => setNewForm({ ...newForm, occurrence_threshold_max: e.target.value })}
                className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5" />
            </label>
            <label className="text-xs text-slate-500">
              {tUi('PA_POLICY_WINDOW_MINUTES_LABEL')}
              <input type="number" value={newForm.window_minutes}
                onChange={e => setNewForm({ ...newForm, window_minutes: e.target.value })}
                className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5" />
            </label>
            <label className="text-xs text-slate-500">
              {tUi('PA_POLICY_PRIORITY_LABEL')}
              <input type="number" value={newForm.priority}
                onChange={e => setNewForm({ ...newForm, priority: e.target.value })}
                className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5" />
            </label>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => create.mutate()}
              disabled={!newForm.severity || create.isPending || (newForm.match_type !== 'DEFAULT' && !newForm.match_value)}
              className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {create.isPending ? '…' : tUi('PA_POLICY_CREATE_RULE')}
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />)}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <p className="text-sm">{tUi('PA_POLICY_RULES_LOAD_FAILED')}</p>
          <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">
            {tUi('CFO_ATTRITION_RETRY')}
          </button>
        </div>
      ) : rules.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <CheckCircle size={40} className="text-emerald-400 mb-3" />
          <p className="font-medium text-slate-600">{tUi('PA_POLICY_RULES_EMPTY')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {rules.map((r: any) => (
            <div key={r.rule_id} className={`bg-white border rounded-xl p-4 ${r.is_active ? 'border-slate-200' : 'border-slate-100 opacity-60'}`}>
              {editId === r.rule_id ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-4 gap-3">
                    <label className="text-xs text-slate-500">
                      {tUi('PA_POLICY_OCCURRENCE_MIN_LABEL')}
                      <input type="number" value={editForm.occurrence_threshold}
                        onChange={e => setEditForm({ ...editForm, occurrence_threshold: e.target.value })}
                        className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5" />
                    </label>
                    <label className="text-xs text-slate-500">
                      {tUi('PA_POLICY_OCCURRENCE_MAX_LABEL')}
                      <input type="number" value={editForm.occurrence_threshold_max}
                        onChange={e => setEditForm({ ...editForm, occurrence_threshold_max: e.target.value })}
                        className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5" />
                    </label>
                    <label className="text-xs text-slate-500">
                      {tUi('PA_POLICY_WINDOW_MINUTES_LABEL')}
                      <input type="number" value={editForm.window_minutes}
                        onChange={e => setEditForm({ ...editForm, window_minutes: e.target.value })}
                        className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5" />
                    </label>
                    <label className="text-xs text-slate-500">
                      {tUi('PA_POLICY_PRIORITY_LABEL')}
                      <input type="number" value={editForm.priority}
                        onChange={e => setEditForm({ ...editForm, priority: e.target.value })}
                        className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5" />
                    </label>
                  </div>
                  <div className="flex items-center gap-4">
                    <label className="text-xs text-slate-500">
                      {tUi('PA_POLICY_SEVERITY_LABEL')}
                      <select value={editForm.severity} onChange={e => setEditForm({ ...editForm, severity: e.target.value })}
                        className="ml-2 text-sm border border-slate-200 rounded-lg px-2 py-1 bg-white">
                        {['P0', 'P1', 'P2', 'P3'].map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </label>
                    <label className="text-xs text-slate-500 flex items-center gap-1.5">
                      <input type="checkbox" checked={editForm.is_active}
                        onChange={e => setEditForm({ ...editForm, is_active: e.target.checked })} />
                      {tUi('PA_POLICY_IS_ACTIVE_LABEL')}
                    </label>
                  </div>
                  <textarea
                    value={editForm.description}
                    onChange={e => setEditForm({ ...editForm, description: e.target.value })}
                    rows={2}
                    placeholder={tUi('PA_POLICY_DESCRIPTION_LABEL')}
                    className="w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5 resize-none"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => update.mutate(r.rule_id)}
                      disabled={update.isPending}
                      className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                      {update.isPending ? '…' : tUi('PA_POLICY_SAVE')}
                    </button>
                    <button
                      onClick={() => setEditId(null)}
                      className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500">
                      {tUi('CISO_SEC_INC_CANCEL')}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0 space-y-1.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-mono text-slate-400">{r.domain}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono">{r.match_type}</span>
                      {r.match_value && <span className="text-xs font-mono text-slate-500">{r.match_value}</span>}
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${SEV_PILL[r.severity] ?? ''}`}>{r.severity}</span>
                      {!r.is_active && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-400">
                          {tUi('PA_POLICY_INACTIVE_BADGE')}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-400 flex-wrap">
                      {r.occurrence_threshold != null && (
                        <span>{tUi('PA_POLICY_OCCURRENCE_MIN_LABEL')}: {r.occurrence_threshold}</span>
                      )}
                      {r.occurrence_threshold_max != null && (
                        <span>{tUi('PA_POLICY_OCCURRENCE_MAX_LABEL')}: {r.occurrence_threshold_max}</span>
                      )}
                      {r.window_minutes != null && (
                        <span>{tUi('PA_POLICY_WINDOW_MINUTES_LABEL')}: {r.window_minutes}</span>
                      )}
                      <span>{tUi('PA_POLICY_PRIORITY_LABEL')}: {r.priority}</span>
                    </div>
                    {r.description && <p className="text-xs text-slate-500">{r.description}</p>}
                  </div>
                  <button
                    onClick={() => startEdit(r)}
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

export function IncidentPolicyConfig() {
  const [tab, setTab] = useState<'sla' | 'rules'>('sla')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
          <Settings size={20} className="text-indigo-500" />
          {tUi('PA_POLICY_TITLE')}
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">{tUi('PA_POLICY_SUB')}</p>
      </div>

      <div className="flex items-center gap-1 border-b border-slate-200">
        <button
          onClick={() => setTab('sla')}
          className={`text-sm px-4 py-2 border-b-2 -mb-px flex items-center gap-1.5 ${
            tab === 'sla' ? 'border-indigo-600 text-indigo-700 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}>
          <Clock size={14} /> {tUi('PA_POLICY_TAB_SLA')}
        </button>
        <button
          onClick={() => setTab('rules')}
          className={`text-sm px-4 py-2 border-b-2 -mb-px flex items-center gap-1.5 ${
            tab === 'rules' ? 'border-indigo-600 text-indigo-700 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}>
          <Filter size={14} /> {tUi('PA_POLICY_TAB_RULES')}
        </button>
      </div>

      {tab === 'sla' ? <SlaTab /> : <RulesTab />}
    </div>
  )
}
