import { useState, useEffect } from 'react'
import { ShieldAlert, X } from 'lucide-react'

interface Props {
  endsAt: string   // ISO timestamp when elevation expires
  onEndEarly: () => void
}

export function ElevationBanner({ endsAt, onEndEarly }: Props) {
  const [remaining, setRemaining] = useState('')

  useEffect(() => {
    function tick() {
      const diff = new Date(endsAt).getTime() - Date.now()
      if (diff <= 0) { setRemaining('Expired'); return }
      const h = Math.floor(diff / 3_600_000)
      const m = Math.floor((diff % 3_600_000) / 60_000)
      const s = Math.floor((diff % 60_000) / 1_000)
      setRemaining(`${h}h ${m}m ${s}s`)
    }
    tick()
    const id = setInterval(tick, 1_000)
    return () => clearInterval(id)
  }, [endsAt])

  return (
    <div className="fixed top-[52px] left-[220px] right-0 z-30 bg-amber-500 px-5 py-2
                    flex items-center gap-3 text-amber-950">
      <ShieldAlert size={16} />
      <span className="text-sm font-medium flex-1">
        Elevated session active — ends in{' '}
        <span className="font-mono font-bold">{remaining}</span>
        {' '}· All actions logged as ELEVATED
      </span>
      <button
        onClick={onEndEarly}
        className="flex items-center gap-1 text-xs font-semibold px-3 py-1
                   bg-amber-950/20 hover:bg-amber-950/40 rounded-md transition-colors"
      >
        <X size={12}/> End early
      </button>
    </div>
  )
}
