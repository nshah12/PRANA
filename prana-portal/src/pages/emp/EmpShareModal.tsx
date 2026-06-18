import { X } from 'lucide-react'

interface Props {
  documentId: string
  onClose: () => void
}

export function EmpShareModal({ documentId, onClose }: Props) {
  const isBulk = documentId === 'bulk'
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-slate-800">{isBulk ? 'Share Documents' : 'Share Document'}</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100">
            <X size={16} className="text-slate-500" />
          </button>
        </div>
        <p className="text-sm text-slate-500">
          {isBulk
            ? 'Select documents and create a shareable link below.'
            : `Create a time-limited shareable link for document ${documentId.slice(0, 8)}…`}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose}
            className="px-4 py-2 text-sm border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50">
            Cancel
          </button>
          <button className="px-4 py-2 text-sm bg-sky-600 text-white rounded-lg hover:bg-sky-700" onClick={onClose}>
            Create Share Link
          </button>
        </div>
      </div>
    </div>
  )
}
