import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LockOpen, Clock } from 'lucide-react'
import { api } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export function AccountLocks() {
  const qc = useQueryClient()

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['ciso-account-locks'],
    queryFn: () => api.get('/v1/ciso/account-locks').then(r => r.data),
    refetchInterval: 60_000,
  })

  const unlockMut = useMutation({
    mutationFn: (event_id: string) =>
      api.post(`/v1/ciso/account-locks/${event_id}/unlock`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ciso-account-locks'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Account Locks</h1>
          <p className="text-sm text-slate-500 mt-0.5">Accounts currently locked by policy. CISO can manually unlock.</p>
        </div>
        <span className="text-xs font-mono text-slate-400">{data?.items?.length ?? 0} locked accounts</span>
      </div>

      {isLoading && (
        <div className="space-y-2 animate-pulse">
          {[...Array(4)].map((_, i) => <div key={i} className="h-16 bg-slate-100 rounded-xl" />)}
        </div>
      )}
      {isError && (
        <div className="text-center py-16 text-slate-400">
          <p className="text-sm">Failed to load account locks.</p>
          <button onClick={() => refetch()} className="mt-2 text-xs text-red-600 hover:underline">Retry</button>
        </div>
      )}

      {!isLoading && !isError && data?.items?.length === 0 && (
        <div className="bg-white rounded-xl border border-slate-100 p-16 text-center">
          <LockOpen size={32} className="text-emerald-400 mx-auto mb-3" />
          <p className="text-slate-500 font-medium">No locked accounts</p>
          <p className="text-xs text-slate-400 mt-1">All accounts are currently active.</p>
        </div>
      )}

      <div className="space-y-3">
        {data?.items?.map((row: any) => {
          const autoUnlockAt = row.scheduled_unlock_at ? new Date(row.scheduled_unlock_at) : null
          const autoUnlockInFuture = autoUnlockAt && autoUnlockAt > new Date()
          return (
            <div key={row.event_id} className="bg-white rounded-xl border border-slate-100 shadow-sm p-5 flex items-start gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-slate-800">{row.identifier}</span>
                  <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                    row.account_type === 'oa_user' ? 'bg-indigo-50 text-indigo-700' : 'bg-sky-50 text-sky-700'
                  }`}>{row.account_type === 'oa_user' ? 'OA User' : 'Employee'}</span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Locked: {fmtDateTime(row.locked_at)}
                  {row.failed_attempt_count ? ` · ${row.failed_attempt_count} failed attempts` : ''}
                  {row.last_failed_ip ? ` · Last IP: ${row.last_failed_ip}` : ''}
                </p>
                {autoUnlockInFuture && (
                  <p className="text-xs text-amber-600 mt-1 flex items-center gap-1">
                    <Clock size={11} />
                    Auto-unlocks {fmtDateTime(row.scheduled_unlock_at)}
                  </p>
                )}
              </div>
              <button
                onClick={() => {
                  if (confirm(`Manually unlock ${row.identifier}?`)) {
                    unlockMut.mutate(row.event_id)
                  }
                }}
                disabled={unlockMut.isPending}
                className="flex items-center gap-1.5 text-xs font-medium text-emerald-700
                           border border-emerald-200 px-3 py-1.5 rounded-lg hover:bg-emerald-50 shrink-0"
              >
                <LockOpen size={12} /> Unlock now
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
