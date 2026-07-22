import { useState } from 'react'
import { FileDown, Plus } from 'lucide-react'
import { api } from '@/lib/api'
import { tUi } from '@/i18n'

const QUICK_REPORTS = [
  { id: 'vault_completeness', label: 'Vault Completeness Summary' },
  { id: 'form16_coverage', label: 'Form-16 Coverage' },
  { id: 'salary_slip_gaps', label: 'Salary Slip Gap Report' },
  { id: 'statutory_compliance', label: 'Statutory Compliance Matrix' },
]

export function ComplianceExport() {
  const [generating, setGenerating] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  async function downloadReport(id: string) {
    setGenerating(id)
    setDownloadError(null)
    try {
      const res = await api.get(`/v1/chro/reports/${id}`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url; a.download = `${id}_${new Date().toISOString().slice(0, 10)}.pdf`
      a.click(); URL.revokeObjectURL(url)
    } catch {
      // BUG FIX: this catch was missing entirely — a failed download became an
      // unhandled promise rejection with no user-facing feedback. Now surfaces
      // a taxonomy-driven error message per row.
      setDownloadError(id)
    } finally { setGenerating(null) }
  }

  return (
    <div className="space-y-6 max-w-xl">
      <h1 className="text-xl font-semibold text-slate-800">{tUi('CHRO_COMPLIANCE_EXPORT_TITLE')}</h1>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-3">
        <h2 className="font-medium text-slate-700 text-sm">{tUi('CHRO_COMPLIANCE_EXPORT_QUICK_REPORTS')}</h2>
        {QUICK_REPORTS.map(r => (
          <div key={r.id} className="p-4 bg-canvas2 rounded-xl">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-700">{r.label}</p>
              <button onClick={() => downloadReport(r.id)}
                      disabled={generating === r.id}
                      className="flex items-center gap-1.5 text-xs font-medium text-violet-600
                                 border border-violet-200 px-3 py-1.5 rounded-lg hover:bg-violet-50
                                 disabled:opacity-40">
                <FileDown size={12}/>
                {generating === r.id ? tUi('CHRO_COMPLIANCE_EXPORT_GENERATING') : tUi('CHRO_COMPLIANCE_EXPORT_DOWNLOAD_PDF')}
              </button>
            </div>
            {downloadError === r.id && (
              <p className="text-xs text-red-600 mt-2">{tUi('CHRO_COMPLIANCE_EXPORT_DOWNLOAD_FAILED')}</p>
            )}
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-6 space-y-4">
        <h2 className="font-medium text-slate-700 text-sm">{tUi('CHRO_COMPLIANCE_EXPORT_CUSTOM_REPORT')}</h2>
        <p className="text-sm text-slate-500">{tUi('CHRO_COMPLIANCE_EXPORT_CUSTOM_SUB')}</p>
        <div className="flex gap-3">
          <input type="date" className="border border-slate-200 rounded-lg px-3 py-2 text-sm
                                       focus:outline-none focus:ring-2 focus:ring-violet-500" />
          <span className="self-center text-slate-400">to</span>
          <input type="date" className="border border-slate-200 rounded-lg px-3 py-2 text-sm
                                       focus:outline-none focus:ring-2 focus:ring-violet-500" />
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white
                           rounded-lg text-sm font-medium hover:bg-violet-700">
          <Plus size={14}/> Generate report
        </button>
      </div>
    </div>
  )
}
