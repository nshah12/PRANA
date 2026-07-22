import { tUi } from '@/i18n'

export const OVERRIDE_REASON_CODES = [
  'SUPPORT_ESCALATION',
  'EMPLOYEE_LOST_DEVICE',
  'SECURITY_INCIDENT',
  'COMPLIANCE_REQUEST',
  'OTHER',
] as const

export type OverrideReasonCode = typeof OVERRIDE_REASON_CODES[number]

const REASON_LABEL_KEY: Record<OverrideReasonCode, string> = {
  SUPPORT_ESCALATION:   'OVERRIDE_REASON_SUPPORT_ESCALATION',
  EMPLOYEE_LOST_DEVICE: 'OVERRIDE_REASON_EMPLOYEE_LOST_DEVICE',
  SECURITY_INCIDENT:    'OVERRIDE_REASON_SECURITY_INCIDENT',
  COMPLIANCE_REQUEST:   'OVERRIDE_REASON_COMPLIANCE_REQUEST',
  OTHER:                'OVERRIDE_REASON_OTHER',
}

interface Props {
  idPrefix: string
  reasonCode: string
  reasonNote: string
  onReasonCodeChange: (code: string) => void
  onReasonNoteChange: (note: string) => void
}

/**
 * Controlled-vocabulary reason capture for PA override actions — mirrors
 * account_status_event.reason_code (fixed set) + reason_note (optional
 * elaboration) so overrides are filterable/reportable, not a single free-text
 * blob. "Other" requires a note so the audit trail never records just "Other".
 */
export function OverrideReasonFields({ idPrefix, reasonCode, reasonNote, onReasonCodeChange, onReasonNoteChange }: Props) {
  const noteRequired = reasonCode === 'OTHER'

  return (
    <>
      <div className="space-y-1">
        <label htmlFor={`${idPrefix}-reason-code`}
               className="text-xs font-medium text-slate-500 uppercase tracking-wide">
          {tUi('PA_RESET_TOTP_REASON_LABEL')} *
        </label>
        <select
          id={`${idPrefix}-reason-code`}
          value={reasonCode}
          onChange={e => onReasonCodeChange(e.target.value)}
          required
          className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white
                     focus:outline-none focus:ring-2 focus:ring-red-400"
        >
          <option value="" disabled>{tUi('OVERRIDE_REASON_CODE_PLACEHOLDER')}</option>
          {OVERRIDE_REASON_CODES.map(code => (
            <option key={code} value={code}>{tUi(REASON_LABEL_KEY[code])}</option>
          ))}
        </select>
      </div>

      <div className="space-y-1">
        <label htmlFor={`${idPrefix}-reason-note`}
               className="text-xs font-medium text-slate-500 uppercase tracking-wide">
          {tUi('OVERRIDE_REASON_NOTE_LABEL')} {noteRequired && '*'}
        </label>
        <input
          id={`${idPrefix}-reason-note`}
          value={reasonNote}
          onChange={e => onReasonNoteChange(e.target.value)}
          required={noteRequired}
          className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm
                     focus:outline-none focus:ring-2 focus:ring-red-400"
        />
      </div>
    </>
  )
}
