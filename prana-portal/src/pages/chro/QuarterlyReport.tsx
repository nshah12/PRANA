import { Download } from 'lucide-react'
import { api } from '@/lib/api'
import { useState } from 'react'

export function QuarterlyReport() {
  const [generating, setGenerating] = useState(false)

  async function download() {
    setGenerating(true)
    try {
      const res = await api.get('/v1/chro/reports/quarterly', { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url; a.download = `PRANA_Quarterly_${new Date().toISOString().slice(0, 7)}.pdf`
      a.click(); URL.revokeObjectURL(url)
    } finally { setGenerating(false) }
  }

  const sections = [
    'Executive Summary', 'QoQ Vault Health Comparison', 'Department Breakdown',
    'Statutory Compliance Table', 'Exit Document Completeness',
    'Employer Brand Metrics', 'Risk & Recommendations', 'Data Residency Certificate',
  ]

  return (
    <div className="space-y-6 max-w-xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Quarterly Report</h1>
        <button onClick={download} disabled={generating}
                className="flex items-center gap-2 px-4 py-2 bg-pink-600 text-white
                           rounded-lg text-sm font-medium hover:bg-pink-700 disabled:opacity-40">
          <Download size={14}/>
          {generating ? 'Generating…' : 'Download 8-page PDF'}
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6">
        <p className="text-sm text-slate-500 mb-4">
          Board-ready 8-page report with QoQ comparison, statutory compliance, and employer brand metrics.
          Digitally signed by PRANA.
        </p>
        <h2 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">Contents</h2>
        <ol className="space-y-2">
          {sections.map((s, i) => (
            <li key={i} className="flex items-center gap-3 text-sm text-slate-700">
              <span className="w-5 h-5 rounded-full bg-pink-100 text-pink-700 text-xs
                               font-bold flex items-center justify-center flex-shrink-0">{i + 1}</span>
              {s}
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}
