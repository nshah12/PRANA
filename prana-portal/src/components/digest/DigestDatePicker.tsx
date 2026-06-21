/**
 * DigestDatePicker — shared date-range control for all digest pages.
 *
 * Enforces backend bounds BEFORE firing the query:
 *   - Max range: 184 days (~6 months)
 *   - Max lookback: 730 days (2 years)
 *   - to_date capped at today
 *   - from_date must be before to_date
 *
 * Shows inline error when user picks an out-of-bounds range so they
 * understand the constraint without hitting the API.
 */
import { useState, useEffect } from 'react'
import { Calendar, Info } from 'lucide-react'

export type Period = 'weekly' | 'monthly' | 'quarterly' | 'custom'

export interface DateWindow {
  from: string  // YYYY-MM-DD
  to:   string  // YYYY-MM-DD (inclusive last day)
}

interface Props {
  accentColor: string          // Tailwind bg class e.g. 'bg-indigo-600'
  accentText:  string          // Tailwind text class e.g. 'text-indigo-600'
  accentBorder: string         // Tailwind border class
  onChange: (window: DateWindow) => void
}

const MAX_RANGE_DAYS   = 184
const MAX_LOOKBACK_DAYS = 730

function toISO(d: Date): string {
  return d.toISOString().split('T')[0]
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d)
  r.setDate(r.getDate() + n)
  return r
}

function diffDays(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86_400_000)
}

function presetWindow(period: Exclude<Period, 'custom'>): DateWindow {
  const today = new Date()
  const days  = { weekly: 7, monthly: 30, quarterly: 91 }[period]
  return { from: toISO(addDays(today, -days)), to: toISO(today) }
}

export function DigestDatePicker({ accentColor, accentText, accentBorder, onChange }: Props) {
  const [period, setPeriod]     = useState<Period>('weekly')
  const [fromVal, setFromVal]   = useState('')
  const [toVal, setToVal]       = useState('')
  const [error, setError]       = useState<string | null>(null)

  const today        = toISO(new Date())
  const minAllowable = toISO(addDays(new Date(), -MAX_LOOKBACK_DAYS))

  // Fire onChange whenever a valid preset is selected
  useEffect(() => {
    if (period !== 'custom') {
      setError(null)
      onChange(presetWindow(period))
    }
  }, [period]) // eslint-disable-line react-hooks/exhaustive-deps

  function validateAndEmit(from: string, to: string) {
    if (!from || !to) return
    const fromDt = new Date(from)
    const toDt   = new Date(to)
    const todayDt = new Date(today)

    if (toDt > todayDt) {
      setError('End date cannot be in the future.')
      return
    }
    if (fromDt >= toDt) {
      setError('Start date must be before end date.')
      return
    }
    const range = diffDays(fromDt, toDt)
    if (range > MAX_RANGE_DAYS) {
      setError(`Max range is ${MAX_RANGE_DAYS} days (~6 months). You selected ${range} days.`)
      return
    }
    const lookback = diffDays(fromDt, todayDt)
    if (lookback > MAX_LOOKBACK_DAYS) {
      setError(`Data is only available for the last 2 years. Choose a start date after ${minAllowable}.`)
      return
    }
    setError(null)
    onChange({ from, to })
  }

  function handleFrom(val: string) {
    setFromVal(val)
    validateAndEmit(val, toVal)
  }

  function handleTo(val: string) {
    setToVal(val)
    validateAndEmit(fromVal, val)
  }

  const tabs: { key: Period; label: string }[] = [
    { key: 'weekly',    label: 'This week' },
    { key: 'monthly',   label: 'This month' },
    { key: 'quarterly', label: 'This quarter' },
    { key: 'custom',    label: 'Custom' },
  ]

  return (
    <div className="space-y-3">
      {/* Period tabs */}
      <div className="flex gap-1.5 flex-wrap">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setPeriod(t.key)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors
              ${period === t.key
                ? `${accentColor} text-white ${accentBorder}`
                : 'text-slate-500 border-slate-200 hover:bg-slate-50'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Custom range inputs */}
      {period === 'custom' && (
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Calendar size={13} className="text-slate-400 flex-shrink-0"/>
            <label htmlFor="digest-from" className="text-xs text-slate-500 w-8">From</label>
            <input
              id="digest-from"
              type="date"
              value={fromVal}
              min={minAllowable}
              max={toVal || today}
              onChange={e => handleFrom(e.target.value)}
              className="text-sm border border-slate-200 rounded-lg px-2.5 py-1.5
                         focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="digest-to" className="text-xs text-slate-500 w-4">To</label>
            <input
              id="digest-to"
              type="date"
              value={toVal}
              min={fromVal || minAllowable}
              max={today}
              onChange={e => handleTo(e.target.value)}
              className="text-sm border border-slate-200 rounded-lg px-2.5 py-1.5
                         focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
        </div>
      )}

      {/* Inline constraint info (always shown for custom) */}
      {period === 'custom' && !error && (
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Info size={11}/>
          Max 6 months per query · data available up to 2 years back
        </div>
      )}

      {/* Error message — shown before API call, not after */}
      {error && (
        <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50
                        border border-red-200 rounded-lg px-3 py-2">
          <Info size={12} className="flex-shrink-0"/>
          {error}
        </div>
      )}
    </div>
  )
}
