import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Search, ChevronDown } from 'lucide-react'

interface Tenant {
  tenant_id: string
  tenant_name: string
  domain: string
  status: string
  industry?: string
  sla_tier?: string
}

interface Props {
  value: string | null
  onChange: (tenantId: string | null, tenant?: Tenant) => void
  placeholder?: string
  className?: string
  disabled?: boolean
}

const STATUS_COLOR: Record<string, string> = {
  ACTIVE:    'bg-emerald-100 text-emerald-700',
  PENDING:   'bg-amber-100 text-amber-700',
  SUSPENDED: 'bg-red-100 text-red-700',
}

export function TenantCombobox({ value, onChange, placeholder = 'Search tenant…', className = '', disabled }: Props) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [displayName, setDisplayName] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['tenant-combobox', q],
    queryFn: () => api.get('/admin/tenants', { params: { q: q || undefined, limit: 20 } }).then(r => r.data),
    staleTime: 30_000,
    enabled: open,
  })
  const tenants: Tenant[] = data?.tenants ?? []

  // Populate display name when value is set externally
  useEffect(() => {
    if (value && tenants.length > 0) {
      const t = tenants.find(t => t.tenant_id === value)
      if (t) setDisplayName(t.tenant_name)
    }
  }, [value, tenants])

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setQ('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  function handleOpen() {
    if (disabled) return
    setOpen(true)
    setQ('')
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  function handleSelect(t: Tenant) {
    setDisplayName(t.tenant_name)
    onChange(t.tenant_id, t)
    setOpen(false)
    setQ('')
  }

  function handleClear(e: React.MouseEvent) {
    e.stopPropagation()
    setDisplayName('')
    onChange(null)
  }

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* Trigger button */}
      <button
        type="button"
        onClick={handleOpen}
        disabled={disabled}
        className={`w-full flex items-center gap-2 border rounded-xl px-3 py-2.5 text-sm text-left
                    transition-colors focus:outline-none
                    ${open ? 'border-amber-400 ring-2 ring-amber-100' : 'border-slate-200 hover:border-slate-300'}
                    ${disabled ? 'bg-slate-50 text-slate-400 cursor-not-allowed' : 'bg-white cursor-pointer'}`}>
        <Search size={13} className="text-slate-400 flex-shrink-0" />
        <span className={`flex-1 truncate ${value ? 'text-slate-800' : 'text-slate-400'}`}>
          {value ? displayName || 'Loading…' : placeholder}
        </span>
        {value && !disabled && (
          <button onClick={handleClear}
            className="text-slate-300 hover:text-slate-500 flex-shrink-0 text-xs leading-none p-0.5">
            ✕
          </button>
        )}
        <ChevronDown size={13} className={`text-slate-400 flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-2xl
                        shadow-xl z-50 overflow-hidden">
          {/* Search input */}
          <div className="p-2 border-b border-slate-100">
            <div className="relative">
              <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                ref={inputRef}
                value={q}
                onChange={e => setQ(e.target.value)}
                placeholder="Type to search…"
                className="w-full pl-7 pr-3 py-2 text-sm border border-slate-200 rounded-xl
                           focus:outline-none focus:ring-2 focus:ring-amber-300"
              />
            </div>
          </div>

          {/* Results */}
          <div className="max-h-60 overflow-y-auto py-1">
            {isLoading && (
              <div className="flex justify-center py-4">
                <div className="w-5 h-5 border-2 border-amber-200 border-t-amber-500 rounded-full animate-spin" />
              </div>
            )}
            {!isLoading && tenants.length === 0 && (
              <p className="text-sm text-slate-400 text-center py-4">No tenants found</p>
            )}
            {tenants.map(t => (
              <button
                key={t.tenant_id}
                type="button"
                onClick={() => handleSelect(t)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-50 transition-colors
                            ${t.tenant_id === value ? 'bg-amber-50' : ''}`}>
                {/* Initials avatar */}
                <div className="w-7 h-7 rounded-lg bg-amber-100 flex items-center justify-center
                                text-amber-700 text-xs font-bold flex-shrink-0">
                  {t.tenant_name.slice(0, 2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 truncate">{t.tenant_name}</p>
                  <p className="text-xs text-slate-400 font-mono truncate">{t.domain}</p>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  {t.sla_tier && (
                    <span className="text-[10px] text-slate-400 bg-slate-100 rounded px-1.5 py-0.5">
                      {t.sla_tier}
                    </span>
                  )}
                  <span className={`text-[10px] font-medium rounded-full px-2 py-0.5 ${STATUS_COLOR[t.status] ?? 'bg-slate-100 text-slate-500'}`}>
                    {t.status}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
