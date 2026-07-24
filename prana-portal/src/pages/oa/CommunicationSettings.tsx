/**
 * CommunicationSettings (OA-Admin) — tenant-scoped only. Mirrors HRMSSettings.tsx's
 * pattern (a dedicated OA-side settings screen for one integration domain). See
 * prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §8.2.
 * Two tabs: Channel Policy (editing writes a tenant override, never the
 * platform default) and Vendor Chain preference (reorder/disable among
 * vendors PA already enabled — no credential fields at all).
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Radio, ListOrdered, Pencil, RotateCcw } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

const CHANNELS = ['email', 'sms', 'whatsapp', 'portal_bell', 'ivr', 'push']

function OrgChannelPolicyTab() {
  const qc = useQueryClient()
  const [editTemplate, setEditTemplate] = useState<string | null>(null)
  const [editChannels, setEditChannels] = useState<string[]>([])

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['org-comm-channel-policy'],
    queryFn: () => api.get('/v1/org/communications/channel-policy').then(r => r.data),
  })

  const update = useMutation({
    mutationFn: ({ templateId, channels }: { templateId: string; channels: string[] }) =>
      api.patch(`/v1/org/communications/channel-policy/${templateId}`, { channels }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['org-comm-channel-policy'] })
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
                  onClick={() => update.mutate({ templateId: item.template_id, channels: editChannels })}
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
                {item.is_tenant_override ? (
                  <span className="text-xs px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700">
                    {tUi('COMM_OVERRIDE_BADGE')}
                  </span>
                ) : (
                  <span className="text-xs px-1.5 py-0.5 rounded-full bg-slate-50 text-slate-400">
                    {tUi('COMM_PLATFORM_DEFAULT_BADGE')}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {item.is_tenant_override && (
                  <button
                    onClick={() => update.mutate({ templateId: item.template_id, channels: item.platform_channels })}
                    disabled={update.isPending}
                    title={tUi('COMM_RESET_TO_PLATFORM')}
                    className="text-xs px-2 py-1.5 border border-slate-200 rounded-lg text-slate-400 hover:bg-slate-50">
                    <RotateCcw size={11} />
                  </button>
                )}
                <button
                  onClick={() => startEdit(item)}
                  className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500 hover:bg-slate-50 flex items-center gap-1">
                  <Pencil size={11} /> {tUi('PA_POLICY_EDIT')}
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function OrgVendorChainTab() {
  const qc = useQueryClient()
  const [editChannel, setEditChannel] = useState<string | null>(null)
  const [editVendors, setEditVendors] = useState<string[]>([])

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['org-comm-vendor-chains'],
    queryFn: () => api.get('/v1/org/communications/vendor-chains').then(r => r.data),
  })

  const update = useMutation({
    mutationFn: (channel: string) =>
      api.patch(`/v1/org/communications/vendor-chains/${channel}`, { vendors: editVendors }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['org-comm-vendor-chains'] })
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
      <p className="text-xs text-slate-400">{tUi('COMM_VENDOR_ENABLED_ONLY_HINT')}</p>
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

export function CommunicationSettings() {
  const [tab, setTab] = useState<'policy' | 'chains'>('policy')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
          <Radio size={20} className="text-indigo-500" />
          {tUi('COMM_SETTINGS_TITLE')}
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">{tUi('COMM_SETTINGS_SUB_OA')}</p>
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
      </div>

      {tab === 'policy' ? <OrgChannelPolicyTab /> : <OrgVendorChainTab />}
    </div>
  )
}
