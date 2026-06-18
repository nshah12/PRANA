import { Bell } from 'lucide-react'

const ANNOUNCEMENTS = [
  {
    id: 1,
    title: 'PRANA Platform v2.1 — DPDP Act 2023 Compliance Module Live',
    date: '2026-06-10',
    category: 'RELEASE',
    body: 'The consent management, data erasure, and grievance workflows are now fully live. All tenants must review and accept the updated DPA before 2026-07-01.',
  },
  {
    id: 2,
    title: 'YugabyteDB upgrade to 2.20.2 — scheduled maintenance',
    date: '2026-06-08',
    category: 'MAINTENANCE',
    body: 'Dual-region failover test scheduled for 2026-06-22 02:00–04:00 IST. Both ap-south-1 (Mumbai) and ap-south-2 (Hyderabad) nodes will be restarted in sequence. No data loss expected.',
  },
  {
    id: 3,
    title: 'New tenant onboarding: PQRS Fintech Pvt Ltd',
    date: '2026-06-05',
    category: 'TENANT',
    body: 'PQRS Fintech (pqrsfintech.in) has been provisioned. KEK created in ap-south-1. OA-Admin account activated.',
  },
  {
    id: 4,
    title: 'AI Pipeline Qwen2.5-14B model update available',
    date: '2026-06-01',
    category: 'AI',
    body: 'A new quantised checkpoint is available from HuggingFace. Benchmark shows 4% improvement in field extraction accuracy on Form 16 documents. Upgrade via prana-ai deploy workflow.',
  },
]

const CAT_COLOR: Record<string, string> = {
  RELEASE:     'bg-indigo-50 text-indigo-700',
  MAINTENANCE: 'bg-amber-50  text-amber-700',
  TENANT:      'bg-emerald-50 text-emerald-700',
  AI:          'bg-violet-50 text-violet-700',
}

export function Announcements() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Bell size={20} className="text-amber-500" />
        <h1 className="text-xl font-semibold text-slate-800">Platform Announcements</h1>
      </div>

      <div className="space-y-4">
        {ANNOUNCEMENTS.map(a => (
          <div key={a.id} className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
            <div className="flex items-start gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full ${CAT_COLOR[a.category] ?? 'bg-slate-100 text-slate-600'}`}>
                    {a.category}
                  </span>
                  <span className="text-xs text-slate-400 font-mono">{a.date}</span>
                </div>
                <h2 className="font-medium text-slate-800 text-sm mb-2">{a.title}</h2>
                <p className="text-sm text-slate-500 leading-relaxed">{a.body}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
