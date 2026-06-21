/**
 * Employee Shares — view, manage, revoke share links.
 * API:
 *   GET    /vault/shares        → { shares: ShareLink[] }
 *   DELETE /vault/shares/{id}   → 204
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Share2, Trash2, ExternalLink, Clock, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { EmpShareModal } from './EmpShareModal'

interface ShareLink {
  token_id: string
  share_url: string
  label: string | null
  expires_at: string
  created_at: string
  view_count: number
  usage_limit: number | null
  document_count: number
  is_active: boolean
}

function formatExpiry(expiresAt: string): string {
  const diff = new Date(expiresAt).getTime() - Date.now()
  if (diff <= 0) return 'Expired'
  const h = Math.floor(diff / 3600000)
  if (h < 24) return `Expires in ${h}h`
  return `Expires ${new Date(expiresAt).toLocaleDateString('en-IN', { day:'2-digit', month:'short' })}`
}

function ExpiryBadge({ expiresAt, isActive }: { expiresAt: string; isActive: boolean }) {
  const expired = new Date(expiresAt) < new Date()
  if (!isActive || expired) return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 text-xs">Revoked / expired</span>
  const h = (new Date(expiresAt).getTime() - Date.now()) / 3600000
  const color = h < 6 ? 'bg-red-50 text-red-600' : h < 24 ? 'bg-amber-50 text-amber-600' : 'bg-emerald-50 text-emerald-600'
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${color}`}><Clock size={10} />{formatExpiry(expiresAt)}</span>
}

export function EmpShares() {
  const qc = useQueryClient()
  const [revokeTarget, setRevokeTarget] = useState<ShareLink | null>(null)
  const [showCreateFor, setShowCreateFor] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['emp-shares'],
    queryFn: () => api.get<{ shares: ShareLink[] }>('/v1/vault/share').then(r => r.data),
  })

  const shares = data?.shares ?? []
  const active = shares.filter(s => s.is_active && new Date(s.expires_at) > new Date())
  const inactive = shares.filter(s => !s.is_active || new Date(s.expires_at) <= new Date())

  const revokeMut = useMutation({
    mutationFn: (id: string) => api.delete(`/v1/vault/shares/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['emp-shares'] }); setRevokeTarget(null) },
  })

  const totalViews = shares.reduce((a, s) => a + s.view_count, 0)

  return (
    <div className="p-6 space-y-5">
      {showCreateFor && <EmpShareModal documentId={showCreateFor} onClose={() => setShowCreateFor(null)} />}

      {/* Revoke confirm modal */}
      {revokeTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6 space-y-4">
            <h3 className="font-semibold text-slate-800">Revoke this link?</h3>
            <p className="text-sm text-slate-500">
              {revokeTarget.label || 'This share link'} will stop working immediately. This cannot be undone.
            </p>
            <div className="flex gap-2">
              <button onClick={() => setRevokeTarget(null)} className="flex-1 border border-slate-200 text-slate-700 rounded-xl py-2 text-sm hover:bg-slate-50">Cancel</button>
              <button
                onClick={() => revokeMut.mutate(revokeTarget.token_id)}
                disabled={revokeMut.isPending}
                className="flex-1 bg-red-600 text-white rounded-xl py-2 text-sm flex items-center justify-center gap-2 hover:bg-red-700 disabled:opacity-50">
                {revokeMut.isPending ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                Revoke
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Shares</h1>
        <p className="text-sm text-slate-500 mt-0.5">{active.length} active · {totalViews} total views · {inactive.length} expired / revoked</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Active links', value: active.length, color: 'text-emerald-600' },
          { label: 'Total views', value: totalViews, color: 'text-indigo-600' },
          { label: 'Expired/Revoked', value: inactive.length, color: 'text-slate-400' },
        ].map(c => (
          <div key={c.label} className="bg-white border border-slate-200 rounded-xl p-4">
            <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
            <p className="text-xs text-slate-500 mt-1">{c.label}</p>
          </div>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-slate-100 animate-pulse rounded-xl" />)}
        </div>
      ) : shares.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <Share2 size={40} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">No share links yet</p>
          <p className="text-xs mt-1">Create one from your Vault to share documents securely.</p>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Active */}
          {active.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Active</p>
              <div className="space-y-2">
                {active.map(s => <ShareCard key={s.token_id} share={s} onRevoke={() => setRevokeTarget(s)} />)}
              </div>
            </div>
          )}

          {/* Inactive */}
          {inactive.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Expired / Revoked</p>
              <div className="space-y-2 opacity-60">
                {inactive.map(s => <ShareCard key={s.token_id} share={s} />)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ShareCard({ share, onRevoke }: { share: ShareLink; onRevoke?: () => void }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-start gap-3">
      <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Share2 size={15} className="text-indigo-500" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm text-slate-800">{share.label || `${share.document_count} document${share.document_count > 1 ? 's' : ''}`}</span>
          <ExpiryBadge expiresAt={share.expires_at} isActive={share.is_active} />
        </div>
        <div className="flex items-center gap-3 mt-1">
          <span className="text-xs text-slate-400">{share.view_count} view{share.view_count !== 1 ? 's' : ''}</span>
          {share.usage_limit && (
            <span className="text-xs text-slate-400">limit {share.usage_limit}</span>
          )}
          <a href={share.share_url} target="_blank" rel="noreferrer"
            className="text-xs text-indigo-500 hover:underline flex items-center gap-0.5">
            Open <ExternalLink size={10} />
          </a>
        </div>
      </div>
      {onRevoke && share.is_active && new Date(share.expires_at) > new Date() && (
        <button onClick={onRevoke}
          className="p-1.5 rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 transition-colors flex-shrink-0">
          <Trash2 size={14} />
        </button>
      )}
    </div>
  )
}
