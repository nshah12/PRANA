import { Construction } from 'lucide-react'

export function StubScreen({ title }: { title: string }) {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-slate-800">{title}</h1>
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm p-12 text-center">
        <Construction size={36} className="mx-auto text-slate-300 mb-3" />
        <p className="text-slate-500 font-medium">{title}</p>
        <p className="text-sm text-slate-400 mt-1">Screen implementation in progress.</p>
      </div>
    </div>
  )
}
