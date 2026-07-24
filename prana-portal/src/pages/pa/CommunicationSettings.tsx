/**
 * CommunicationSettings (PA) — full control, platform-wide.
 * Backed by notification_channel_policy + {channel}_vendor_chain config keys
 * (services/communication_settings_service.py). See
 * prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §8.1.
 * Three tabs: Channel Policy (per NotificationTemplate), Vendor Chains
 * (ordered fallback per channel), Vendor Credentials (write-only rotation —
 * a value can be set but is never displayed once saved; never shown to
 * OA-Admin at all — no equivalent route exists on the org/ side).
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Radio, ListOrdered, KeyRound, Pencil, ShieldCheck, ShieldOff } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

const CHANNELS = ['email', 'sms', 'whatsapp', 'portal_bell', 'ivr', 'push']

function ChannelPolicyTab() {
  const qc = useQueryClient()
  const [editTemplate, setEditTemplate] = useState<string | null>(null)
  const [editChannels, setEditChannels] = useState<string[]>([])

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-comm-channel-policy'],
    queryFn: () => api.get('/admin/communications/channel-policy').then(r => r.data),
  })

  const update = useMutation({
    mutationFn: (templateId: string) =>
      api.patch(`/admin/communications/channel-policy/${templateId}`, { channels: editChannels }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-comm-channel-policy'] })
      setEditTemplate(null)
    },
  })

  const items: any[] = data?.items ?? []

  function startEdit(item: any) {
    setEditTemplate(item.template_id)
    setEditChannels(item.channels)
  }

  function toggleChannel(ch: string) {
    setEditChannels(prev => prev.includes(ch) ? prev.filter(c => c !== ch) : [...prev, ch])
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(6)].map((_, i) => <div key={i} className="h-14 bg-slate-100 rounded-xl animate-pulse" />)}
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex flex-col items-center py-16 text-slate-400">
        <p className="text-sm">{tUi('COMM_POLICY_LOAD_FAILED')}</p>
        <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">
          {tUi('CFO_ATTRITION_RETRY')}
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {items.map((item: any) => (
        <div key={item.template_id} className="bg-white border border-slate-200 rounded-xl p-3">
          {editTemplate === item.template_id ? (
            <div className="space-y-3">
              <span className="text-xs font-mono text-slate-600">{item.template_id}</span>
              <div className="flex flex-wrap gap-2">
                {CHANNELS.map(ch => (
                  <label key={ch} className="text-xs flex items-center gap-1.5 border border-slate-200 rounded-lg px-2 py-1 cursor-pointer">
                    <input type="checkbox" checked={editChannels.includes(ch)} onChange={() => toggleChannel(ch)} />
                    {ch}
                  </label>
                ))}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => update.mutate(item.template_id)}
                  disabled={editChannels.length === 0 || update.isPending}
                  className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                  {update.isPending ? '…' : tUi('PA_POLICY_SAVE')}
                </button>
                <button
                  onClick={() => setEditTemplate(null)}
                  className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500">
                  {tUi('CISO_SEC_INC_CANCEL')}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-4">
              <div className="flex-1 min-w-0 flex items-center gap-2 flex-wrap">
                <span className="text-xs font-mono text-slate-600">{item.template_id}</span>
                {item.channels.map((ch: string) => (
                  <span key={ch} className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{ch}</span>
                ))}
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
  )
}

function VendorChainsTab() {
  const qc = useQueryClient()
  const [editChannel, setEditChannel] = useState<string | null>(null)
  const [editVendors, setEditVendors] = useState<string[]>([])

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-comm-vendor-chains'],
    queryFn: () => api.get('/admin/communications/vendor-chains').then(r => r.data),
  })

  const update = useMutation({
    mutationFn: (channel: string) =>
      api.patch(`/admin/communications/vendor-chains/${channel}`, { vendors: editVendors }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-comm-vendor-chains'] })
      setEditChannel(null)
    },
  })

  const chains: Record<string, { chain: string[]; available_vendors: string[] }> = data?.chains ?? {}

  function startEdit(channel: string, chain: string[]) {
    setEditChannel(channel)
    setEditVendors(chain)
  }

  function toggleVendor(v: string) {
    setEditVendors(prev => prev.includes(v) ? prev.filter(x => x !== v) : [...prev, v])
  }

  function moveVendor(i: number, dir: -1 | 1) {
    setEditVendors(prev => {
      const next = [...prev]
      const j = i + dir
      if (j < 0 || j >= next.length) return prev
      ;[next[i], next[j]] = [next[j], next[i]]
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(4)].map((_, i) => <div key={i} className="h-16 bg-slate-100 rounded-xl animate-pulse" />)}
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex flex-col items-center py-16 text-slate-400">
        <p className="text-sm">{tUi('COMM_CHAINS_LOAD_FAILED')}</p>
        <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">
          {tUi('CFO_ATTRITION_RETRY')}
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-400">{tUi('COMM_CHAIN_ORDER_HINT')}</p>
      {Object.entries(chains).map(([channel, info]) => (
        <div key={channel} className="bg-white border border-slate-200 rounded-xl p-3">
          {editChannel === channel ? (
            <div className="space-y-3">
              <span className="text-xs font-mono text-slate-600 uppercase">{channel}</span>
              <div className="flex flex-wrap gap-2">
                {info.available_vendors.map(v => (
                  <label key={v} className="text-xs flex items-center gap-1.5 border border-slate-200 rounded-lg px-2 py-1 cursor-pointer">
                    <input type="checkbox" checked={editVendors.includes(v)} onChange={() => toggleVendor(v)} />
                    {v}
                  </label>
                ))}
              </div>
              {editVendors.length > 0 && (
                <ol className="flex items-center gap-1 text-xs">
                  {editVendors.map((v, i) => (
                    <li key={v} className="flex items-center gap-1 bg-slate-100 rounded-lg px-2 py-1">
                      <span className="font-mono text-slate-500">{i + 1}.</span> {v}
                      <button onClick={() => moveVendor(i, -1)} disabled={i === 0} className="disabled:opacity-30">↑</button>
                      <button onClick={() => moveVendor(i, 1)} disabled={i === editVendors.length - 1} className="disabled:opacity-30">↓</button>
                    </li>
                  ))}
                </ol>
              )}
              <div className="flex gap-2">
                <button
                  onClick={() => update.mutate(channel)}
                  disabled={editVendors.length === 0 || update.isPending}
                  className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                  {update.isPending ? '…' : tUi('PA_POLICY_SAVE')}
                </button>
                <button
                  onClick={() => setEditChannel(null)}
                  className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500">
                  {tUi('CISO_SEC_INC_CANCEL')}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-4">
              <div className="flex-1 min-w-0 flex items-center gap-2">
                <span className="text-xs font-mono text-slate-600 uppercase w-20 shrink-0">{channel}</span>
                <ol className="flex items-center gap-1 flex-wrap">
                  {info.chain.map((v, i) => (
                    <li key={v} className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                      {i + 1}. {v}
                    </li>
                  ))}
                </ol>
              </div>
              <button
                onClick={() => startEdit(channel, info.chain)}
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

function VendorCredentialsTab() {
  const qc = useQueryClient()
  const [editField, setEditField] = useState<string | null>(null)   // `${vendor}:${field_name}`
  const [value, setValue] = useState('')

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-comm-vendor-credentials'],
    queryFn: () => api.get('/admin/communications/vendor-credentials').then(r => r.data),
  })

  const update = useMutation({
    mutationFn: ({ vendor, fieldName }: { vendor: string; fieldName: string }) =>
      api.patch(`/admin/communications/vendor-credentials/${vendor}`, { field_name: fieldName, value }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pa-comm-vendor-credentials'] })
      setEditField(null)
      setValue('')
    },
  })

  const vendors: Record<string, { configured: boolean; source: string }> = data?.vendors ?? {}
  const editableFields: Record<string, string[]> = data?.editable_fields ?? {}

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(6)].map((_, i) => <div key={i} className="h-12 bg-slate-100 rounded-xl animate-pulse" />)}
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex flex-col items-center py-16 text-slate-400">
        <p className="text-sm">{tUi('COMM_CREDENTIALS_LOAD_FAILED')}</p>
        <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">
          {tUi('CFO_ATTRITION_RETRY')}
        </button>
      </div>
    )
  }

  function startEdit(vendor: string, field: string) {
    setEditField(`${vendor}:${field}`)
    setValue('')
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-400">{tUi('COMM_CREDENTIALS_HINT')}</p>
      <div className="space-y-2">
        {Object.entries(vendors).map(([vendor, status]) => (
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

            {(editableFields[vendor] ?? []).length > 0 && (
              <div className="space-y-1.5 pt-2 border-t border-slate-100">
                {editableFields[vendor].map(field => (
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
                          onClick={() => update.mutate({ vendor, fieldName: field })}
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
  )
}

export function CommunicationSettings() {
  const [tab, setTab] = useState<'policy' | 'chains' | 'credentials'>('policy')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
          <Radio size={20} className="text-indigo-500" />
          {tUi('COMM_SETTINGS_TITLE')}
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">{tUi('COMM_SETTINGS_SUB_PA')}</p>
      </div>

      <div className="flex items-center gap-1 border-b border-slate-200">
        <button
          onClick={() => setTab('policy')}
          className={`text-sm px-4 py-2 border-b-2 -mb-px flex items-center gap-1.5 ${
            tab === 'policy' ? 'border-indigo-600 text-indigo-700 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}>
          <Radio size={14} /> {tUi('COMM_TAB_CHANNEL_POLICY')}
        </button>
        <button
          onClick={() => setTab('chains')}
          className={`text-sm px-4 py-2 border-b-2 -mb-px flex items-center gap-1.5 ${
            tab === 'chains' ? 'border-indigo-600 text-indigo-700 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}>
          <ListOrdered size={14} /> {tUi('COMM_TAB_VENDOR_CHAINS')}
        </button>
        <button
          onClick={() => setTab('credentials')}
          className={`text-sm px-4 py-2 border-b-2 -mb-px flex items-center gap-1.5 ${
            tab === 'credentials' ? 'border-indigo-600 text-indigo-700 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}>
          <KeyRound size={14} /> {tUi('COMM_TAB_VENDOR_CREDENTIALS')}
        </button>
      </div>

      {tab === 'policy' ? <ChannelPolicyTab /> : tab === 'chains' ? <VendorChainsTab /> : <VendorCredentialsTab />}
    </div>
  )
}
