import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Upload, Share2, Download, Copy, Check } from 'lucide-react'
import { api } from '@/lib/api'
import { EmpShareModal } from './EmpShareModal'

const DOC_ICON: Record<string, string> = {
  SALARY_SLIP: '📄', FORM_16: '🧾', OFFER_LETTER: '📃',
  APPOINTMENT_LETTER: '📃', RELIEVING_LETTER: '📃', EXPERIENCE_LETTER: '📃',
  INCREMENT_LETTER: '📃', PROMOTION_LETTER: '📃',
}
const ORG_COLORS = ['#0EA5E9','#10B981','#F59E0B','#8B5CF6','#EF4444']
const ORG_BG     = ['rgba(14,165,233,0.08)','rgba(16,185,129,0.08)','rgba(245,158,11,0.08)','rgba(139,92,246,0.08)','rgba(239,68,68,0.08)']
const ORG_BORDER = ['rgba(14,165,233,0.2)','rgba(16,185,129,0.2)','rgba(245,158,11,0.2)','rgba(139,92,246,0.2)','rgba(239,68,68,0.2)']

function fmtDate(d: string | null) {
  if (!d) return 'Present'
  return new Date(d).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
}
function fmtPushed(d: string | null) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function EmpVault() {
  const [filter, setFilter]         = useState('all')
  const [search, setSearch]         = useState('')
  const [copied, setCopied]         = useState(false)
  const [shareDocId, setShareDocId] = useState<string | null>(null)

  const { data: profileData } = useQuery({
    queryKey: ['emp-vault-profile'],
    queryFn: () => api.get('/vault/profile').then(r => r.data),
  })
  const { data: docsData, isLoading } = useQuery({
    queryKey: ['emp-vault-docs'],
    queryFn: () => api.get('/vault/documents', { params: { limit: 100 } }).then(r => r.data),
  })
  const { data: sharesData } = useQuery({
    queryKey: ['emp-vault-shares'],
    queryFn: () => api.get('/vault/share').then(r => r.data),
  })

  const employers: any[] = (profileData?.employers ?? []).slice().sort((a: any, b: any) =>
    new Date(a.doj ?? 0).getTime() - new Date(b.doj ?? 0).getTime()
  )
  const docs: any[]       = docsData?.documents ?? []
  const shares: any[]     = sharesData?.shares ?? []
  const activeShares      = shares.filter((s: any) => s.is_active && new Date(s.expires_at) > new Date())
  const vaultUrl          = profileData?.vault_url ?? 'prana.in/vault/—'
  const activeSince       = profileData?.active_since
    ? new Date(profileData.active_since).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
    : '—'
  const selfUploads       = docs.filter(d => d.is_self_upload)

  // Filter pills
  const pills = [
    { id: 'all', label: 'All', color: undefined },
    ...employers.map((e: any, i: number) => ({
      id: `org:${e.tenant_id ?? e.id}`,
      label: (e.tenant_name ?? e.name ?? '').split(' ')[0],
      color: ORG_COLORS[i % ORG_COLORS.length],
    })),
    { id: 'type:SALARY_SLIP', label: 'Salary Slips', color: undefined },
    { id: 'type:FORM_16',     label: 'Tax Docs',     color: undefined },
    { id: 'type:LETTER',      label: 'Letters',      color: undefined },
  ]

  const filtered = docs.filter(d => {
    if (filter.startsWith('org:')) {
      if (d.tenant_id !== filter.slice(4)) return false
    } else if (filter === 'type:SALARY_SLIP') {
      if (d.doc_type !== 'SALARY_SLIP') return false
    } else if (filter === 'type:FORM_16') {
      if (d.doc_type !== 'FORM_16') return false
    } else if (filter === 'type:LETTER') {
      if (!d.doc_type?.includes('LETTER')) return false
    }
    if (search) {
      const q = search.toLowerCase()
      return (
        d.doc_type?.toLowerCase().includes(q) ||
        d.doc_period?.toLowerCase().includes(q) ||
        (d.tenant_name ?? '').toLowerCase().includes(q)
      )
    }
    return true
  })

  const byOrg = employers.map((e: any, i: number) => ({
    ...e, colorIdx: i,
    docs: filtered.filter(d => d.tenant_id === (e.tenant_id ?? e.id)),
  })).filter(g => g.docs.length > 0)

  function copyUrl() {
    navigator.clipboard.writeText(`https://${vaultUrl}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="p-6">
      {shareDocId && <EmpShareModal documentId={shareDocId} onClose={() => setShareDocId(null)} />}

      {/* Header */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-slate-800">My Vault</h1>
          <p className="text-sm text-slate-500 mt-0.5">All your employment documents — across every employer, in one place</p>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-1.5 px-3 py-2 text-sm border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 transition-colors">
            <Upload size={14} /> Upload
          </button>
          <button className="flex items-center gap-1.5 px-3 py-2 text-sm bg-sky-600 text-white rounded-lg hover:bg-sky-700 transition-colors">
            <Share2 size={14} /> Share Documents
          </button>
        </div>
      </div>

      {/* Vault URL dark gradient card */}
      <div className="rounded-2xl p-5 mb-5 flex items-center justify-between gap-4"
        style={{ background: 'linear-gradient(135deg,#0f172a 0%,#1e3a5f 60%,#0c4a6e 100%)' }}>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-sky-400 mb-1.5">Your Permanent Vault URL</p>
          <p className="text-base font-mono font-bold text-white truncate">{vaultUrl}</p>
          <p className="text-[11px] text-slate-400 mt-1.5 font-mono">
            Active since {activeSince} · {employers.length} linked employer{employers.length !== 1 ? 's' : ''} · {docs.length} documents
          </p>
        </div>
        <button onClick={copyUrl}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold shrink-0 transition-all"
          style={{ background:'rgba(14,165,233,0.15)', color:'#38bdf8', border:'1px solid rgba(14,165,233,0.3)' }}>
          {copied ? <><Check size={13}/> Copied!</> : <><Copy size={13}/> Copy URL</>}
        </button>
      </div>

      {/* 4 stat cards */}
      <div className="grid grid-cols-4 gap-3 mb-5">
        {[
          { val: docs.length,         sub: `${employers.length} employer${employers.length!==1?'s':''}${selfUploads.length?' + '+selfUploads.length+' self':''}`, label: 'Total Documents', color: '#0EA5E9' },
          { val: activeShares.length, sub: activeShares.filter((s:any)=>(new Date(s.expires_at).getTime()-Date.now())<7*86400000).length + ' expiring this week', label: 'Active Shares', color: '#10B981' },
          { val: employers.length,    sub: employers.filter((e:any)=>!e.dol).length+' active · '+employers.filter((e:any)=>e.dol).length+' alumni', label: 'Linked Employers', color: '#F59E0B' },
          { val: selfUploads.length,  sub: 'Uploaded by you', label: 'Self Uploads', color: '#8B5CF6' },
        ].map(s => (
          <div key={s.label} className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
            <p className="text-3xl font-bold" style={{ color: s.color }}>{s.val}</p>
            <p className="text-xs font-semibold text-slate-700 mt-1.5">{s.label}</p>
            <p className="text-[10px] text-slate-400 mt-0.5">{s.sub}</p>
          </div>
        ))}
      </div>

      {/* Filter pills + search */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        {pills.map(p => {
          const active = filter === p.id
          const col    = p.color ?? '#0EA5E9'
          return (
            <button key={p.id} onClick={() => setFilter(p.id)}
              className="px-3 py-1.5 rounded-full text-xs font-semibold border transition-all"
              style={active
                ? { background: col, color: '#fff', borderColor: col }
                : { background: '#fff', color: '#475569', borderColor: '#e2e8f0' }
              }>
              {p.label}
            </button>
          )
        })}
        <div className="ml-auto">
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search documents…"
            className="pl-3 pr-3 py-1.5 text-xs border border-slate-200 rounded-full outline-none focus:border-sky-400 w-48 transition-colors" />
        </div>
      </div>

      {/* Document groups */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_,i) => <div key={i} className="h-32 bg-slate-100 animate-pulse rounded-xl"/>)}
        </div>
      ) : byOrg.length === 0 ? (
        <div className="text-center py-20 text-slate-400">
          <div className="text-4xl mb-3">📂</div>
          <p className="font-medium text-slate-600">No documents found</p>
          <p className="text-sm mt-1">Try a different filter or search term.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {byOrg.map(org => {
            const i   = org.colorIdx
            const col = ORG_COLORS[i % ORG_COLORS.length]
            const bg  = ORG_BG[i % ORG_BG.length]
            const bdr = ORG_BORDER[i % ORG_BORDER.length]
            const isActive = !org.dol
            return (
              <div key={org.tenant_id ?? org.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                {/* Employer section header */}
                <div className="flex items-center gap-3 px-4 py-3"
                  style={{ background: bg, borderBottom: `1px solid ${bdr}` }}>
                  <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: col }}/>
                  <span className="text-sm font-bold text-slate-800">{org.tenant_name ?? org.name}</span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    {fmtDate(org.doj ?? org.from)} – {fmtDate(org.dol ?? org.to)}
                  </span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border"
                    style={isActive
                      ? { background:'rgba(16,185,129,0.1)', color:'#059669', borderColor:'rgba(16,185,129,0.3)' }
                      : { background:'rgba(148,163,184,0.1)', color:'#64748b', borderColor:'#e2e8f0' }
                    }>
                    {isActive ? 'Active' : 'Alumni'}
                  </span>
                  <span className="ml-auto text-[11px] font-medium text-slate-400">{org.docs.length} documents</span>
                </div>

                {/* Doc rows */}
                {org.docs.map((d: any, di: number) => (
                  <div key={d.document_id}
                    className="group flex items-center gap-3 px-4 py-3 hover:bg-slate-50 transition-colors cursor-default"
                    style={di < org.docs.length-1 ? { borderBottom:'1px solid #f1f5f9' } : {}}>
                    {/* Emoji icon box */}
                    <div className="w-9 h-9 rounded-lg flex items-center justify-center text-lg shrink-0"
                      style={{ background: bg }}>
                      {DOC_ICON[d.doc_type] ?? '📄'}
                    </div>

                    {/* Name + meta */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-800">
                        {d.doc_type?.replace(/_/g,' ')}
                        {d.doc_period && <span className="ml-1.5 text-slate-400 font-normal">· {d.doc_period}</span>}
                      </p>
                      <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                        {d.original_filename ?? d.doc_type} · pushed {fmtPushed(d.pushed_at)}
                      </p>
                    </div>

                    {/* Org badge */}
                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0"
                      style={{ background: bg, color: col, border: `1px solid ${bdr}` }}>
                      {(org.tenant_name ?? org.name ?? '').split(' ')[0]}
                    </span>

                    {/* Verified / Self badge */}
                    {!d.is_self_upload
                      ? <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0"
                          style={{ background:'rgba(16,185,129,0.08)', color:'#059669', borderColor:'rgba(16,185,129,0.25)' }}>
                          ✓ Verified
                        </span>
                      : <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0"
                          style={{ background:'rgba(148,163,184,0.08)', color:'#64748b', borderColor:'#e2e8f0' }}>
                          Unverified
                        </span>
                    }

                    {/* Hover actions */}
                    <div className="hidden group-hover:flex items-center gap-1.5 shrink-0">
                      <a href={`/api/vault/documents/${d.document_id}?download=true`}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-slate-600 hover:bg-slate-100 transition-colors">
                        <Download size={11}/> Download
                      </a>
                      <button onClick={() => setShareDocId(d.document_id)}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-sky-600 text-white hover:bg-sky-700 transition-colors">
                        <Share2 size={11}/> Share
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
