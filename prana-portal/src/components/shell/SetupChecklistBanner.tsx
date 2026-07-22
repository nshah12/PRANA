import { CheckSquare } from 'lucide-react'
import { Link } from 'react-router-dom'
import { tUi } from '@/i18n'

interface Props {
  missingCount: number
  top: number
}

/**
 * Persistent, non-dismissible banner while the Go-Live Checklist has
 * incomplete required items — modeled on ElevationBanner.tsx, the Portal's
 * one existing persistent-banner pattern. `top` lets PortalLayout stack this
 * below ElevationBanner when both are visible at once.
 */
export function SetupChecklistBanner({ missingCount, top }: Props) {
  return (
    <div
      className="fixed left-[220px] right-0 z-30 bg-rose-500 px-5 py-2
                 flex items-center gap-3 text-rose-950"
      style={{ top }}
    >
      <CheckSquare size={16} />
      <span className="text-sm font-medium flex-1">
        {tUi('SETUP_CHECKLIST_BANNER_TEXT', { n: missingCount })}
      </span>
      <Link
        to="/org/setup-checklist"
        className="flex items-center gap-1 text-xs font-semibold px-3 py-1
                   bg-rose-950/20 hover:bg-rose-950/40 rounded-md transition-colors"
      >
        {tUi('SETUP_CHECKLIST_BANNER_LINK')}
      </Link>
    </div>
  )
}
