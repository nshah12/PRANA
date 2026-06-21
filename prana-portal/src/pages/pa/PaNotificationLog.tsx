/**
 * PaNotificationLog — Portal Admin cross-tenant notification audit log.
 * Backed by migration-017 `notification_log` table.
 * PA sees all tenants; filters by tenant_id, channel, event_type, status.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bell, Filter, CheckCircle, XCircle, Clock, Globe } from 'lucide-react'
import { api } from '@/lib/api'

const CHANNEL_STYLE: Record<string, string> = {
  EMAIL:       'bg-blue-50 text-blue-700',
  SMS:         'bg-green-50 text-green-700',
  WHATSAPP:    'bg-emerald-50 text-emerald-700',
  PUSH:        'bg-indigo-50 text-indigo-700',
  PORTAL_BELL: 'bg-slate-100 text-slate-600',
}

const STATUS_ICON: Record<string, React.ReactNode> = {
  SENT:       <CheckCircle size={13} className="text-emerald-500" />,
  FAILED:     <XCircle size={13} className="text-red-500" />,
  BOUNCED:    <XCircle size={13} className="text-orange-500" />,
  SUPPRESSED: <XCircle size={13} className="text-slate-400" />,
  QUEUED:     <Clock size={13} className="text-amber-500" />,
}

export function PaNotificationLog() {
  const [tenantId, setTenantId]   = useState('')
  const [channel, setChannel]     = useState('')
  const [eventType, setEventType] = useState('')
  const [notifStatus, setNotifStatus] = useState('')
  const [limit, setLimit]         = useState(100)

  const params = new URLSearchParams({ limit: String(limit) })
  if (tenantId)    params.set('tenant_id', tenantId)
  if (channel)     params.set('channel', channel)
  if (eventType)   params.set('event_type', eventType)
  if (notifStatus) params.set('notif_status', notifStatus)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['pa-notif-log', tenantId, channel, eventType, notifStatus, limit],
    queryFn:  () => api.get(`/admin/notifications?${params}`).then(r => r.data),
  })

  const rows: any[] = data?.items ?? []

  const sentCount    = rows.filter(r => r.status === 'SENT').length
  const failedCount  = rows.filter(r => ['FAILED','BOUNCED'].includes(r.status)).length
  const queuedCount  = rows.filter(r => r.status === 'QUEUED').length

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
            <Bell size={20} className="text-indigo-500" />
            Notification Audit Log
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            All outbound notifications across all tenants · 2-year hot retention
          </p>
        </div>
        <button onClick={() => refetch()}
          className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg text-slate-500 hover:bg-slate-50">
          Refresh
        </button>
      </div>

      {/* Delivery summary */}
      {!isLoading && (
        <div className="flex items-center gap-6 text-sm bg-white rounded-xl border border-slate-100 px-5 py-3.5">
          <span className="flex items-center gap-1.5 text-emerald-600">
            <CheckCircle size={14} /> {sentCount} delivered
          </span>
          <span className="flex items-center gap-1.5 text-red-500">
            <XCircle size={14} /> {failedCount} failed / bounced
          </span>
          <span className="flex items-center gap-1.5 text-amber-500">
            <Clock size={14} /> {queuedCount} queued
          </span>
          <span className="text-slate-400 ml-auto">{rows.length} rows shown</span>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Filter size={14} className="text-slate-400" />
        <div className="flex items-center gap-1.5">
          <Globe size={12} className="text-slate-400" />
          <input
            value={tenantId}
            onChange={e => setTenantId(e.target.value)}
            placeholder="Tenant UUID…"
            className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 w-48 text-slate-600"
          />
        </div>
        <select value={channel} onChange={e => setChannel(e.target.value)}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600 bg-white">
          <option value="">All channels</option>
          {['EMAIL','SMS','WHATSAPP','PUSH','PORTAL_BELL'].map(c => <option key={c}>{c}</option>)}
        </select>
        <select value={eventType} onChange={e => setEventType(e.target.value)}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600 bg-white">
          <option value="">All event types</option>
          {['ANOMALY_DETECTED','ACCOUNT_LOCKED','DOCUMENT_ROUTED','EXCEPTION_RAISED',
            'ELEVATION_APPROVED','ELEVATION_DENIED','DIGEST_READY','DPDP_ERASURE_COMPLETE',
            'DPDP_EXPORT_READY','OA_USER_CREATED'].map(e => <option key={e}>{e}</option>)}
        </select>
        <select value={notifStatus} onChange={e => setNotifStatus(e.target.value)}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600 bg-white">
          <option value="">All statuses</option>
          {['QUEUED','SENT','FAILED','BOUNCED','SUPPRESSED'].map(s => <option key={s}>{s}</option>)}
        </select>
        <select value={limit} onChange={e => setLimit(Number(e.target.value))}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600 bg-white">
          {[100,200].map(n => <option key={n} value={n}>Last {n}</option>)}
        </select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => <div key={i} className="h-10 bg-slate-100 rounded animate-pulse" />)}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <p className="text-sm">Failed to load notification log.</p>
          <button onClick={() => refetch()} className="mt-3 text-xs text-indigo-600 hover:underline">Retry</button>
        </div>
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-slate-400">
          <Bell size={36} className="mb-3 text-slate-300" />
          <p className="text-sm">No notifications match this filter.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-100 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="text-left px-4 py-2.5 text-slate-500 font-medium whitespace-nowrap">When</th>
                  <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Tenant</th>
                  <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Event</th>
                  <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Channel</th>
                  <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Recipient</th>
                  <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Template</th>
                  <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Status</th>
                  <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Retries</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {rows.map((row: any) => (
                  <tr key={row.notification_id} className="hover:bg-slate-50/50">
                    <td className="px-4 py-2.5 font-mono text-slate-500 whitespace-nowrap">
                      {new Date(row.created_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-slate-400 text-xs">
                      {row.tenant_id ? row.tenant_id.slice(0, 8) + '…' : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-slate-700 font-medium whitespace-nowrap">{row.event_type}</td>
                    <td className="px-4 py-2.5">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${CHANNEL_STYLE[row.channel] ?? 'bg-slate-100 text-slate-600'}`}>
                        {row.channel}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-slate-500 font-mono max-w-[140px] truncate">
                      {row.recipient_email ?? row.recipient_phone ?? row.recipient_id?.slice(0, 8)}
                    </td>
                    <td className="px-4 py-2.5 text-slate-500 font-mono whitespace-nowrap">{row.template_id}</td>
                    <td className="px-4 py-2.5">
                      <span className="flex items-center gap-1 whitespace-nowrap">
                        {STATUS_ICON[row.status]}
                        <span className="text-slate-600">{row.status}</span>
                      </span>
                      {row.error_message && (
                        <span className="text-red-500 block truncate max-w-[110px]" title={row.error_message}>
                          {row.error_message}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-slate-500 text-center">{row.retry_count ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
