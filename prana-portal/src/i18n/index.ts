/**
 * PRANA Portal — typed translation helper.
 *
 * Zero runtime dependencies. No i18n library to bundle.
 * The active locale JSON is loaded once and cached in module scope.
 * Adding a language = add <locale>.json, call setLocale("<locale>").
 *
 * Usage:
 *   import { t } from '@/i18n'
 *   t('error', 'INVALID_TOTP')                    // → "Incorrect authenticator code. Please try again."
 *   t('success', 'DOC_UPLOADED')                  // → "Document uploaded. Processing will begin shortly."
 *   t('info', 'SESSION_EXPIRING_SOON', { minutes: 5 })  // → "Your session will expire in 5 minutes."
 *   t('status', 'QUEUED')                         // → "Queued"
 *   t('validation', 'FIELD_REQUIRED')             // → "This field is required."
 */

export type MessageCategory =
  | 'error'
  | 'success'
  | 'info'
  | 'validation'
  | 'status'
  | 'pipeline_error'
  | 'ask_error'
  | 'ui'

type LocaleData = Record<MessageCategory, Record<string, string>>

let _locale: string = 'en'
let _messages: LocaleData | null = null

async function _load(locale: string): Promise<LocaleData> {
  const mod = await import(`./${locale}.json`)
  return mod.default as LocaleData
}

/** Call once at app bootstrap. Defaults to 'en' if not called. */
export async function setLocale(locale: string): Promise<void> {
  _locale = locale
  _messages = await _load(locale)
}

function _getMessages(): LocaleData {
  if (!_messages) {
    // Synchronous fallback — load en.json eagerly via require (CJS/bundler path)
    // In Vite the JSON import is synchronous after bundling
    _messages = require('./en.json') as LocaleData
  }
  return _messages
}

/**
 * Translate a typed code to a display string.
 *
 * @param category  - The message category (error, success, info, etc.)
 * @param code      - The typed code string (e.g. 'INVALID_TOTP')
 * @param vars      - Optional interpolation variables ({minutes: 5} → replaces {minutes})
 * @returns         - Translated string, or the code itself if not found (safe fallback)
 */
export function t(
  category: MessageCategory,
  code: string,
  vars?: Record<string, string | number>,
): string {
  const messages = _getMessages()
  const section = messages[category]
  if (!section) return code

  let str = section[code]
  if (!str) return code  // safe fallback — shows the code if locale is missing an entry

  if (vars) {
    for (const [key, value] of Object.entries(vars)) {
      str = str.replaceAll(`{${key}}`, String(value))
    }
  }

  return str
}

/** Convenience: translate an API error detail string. */
export function tError(code: string, vars?: Record<string, string | number>): string {
  return t('error', code, vars)
}

/** Convenience: translate a success message code. */
export function tSuccess(code: string, vars?: Record<string, string | number>): string {
  return t('success', code, vars)
}

/** Convenience: translate a pipeline status code for UI labels. */
export function tStatus(code: string): string {
  return t('status', code)
}

/** Convenience: translate a validation error code. */
export function tValidation(code: string, vars?: Record<string, string | number>): string {
  return t('validation', code, vars)
}

/** Convenience: translate an informational / progress code. */
export function tInfo(code: string, vars?: Record<string, string | number>): string {
  return t('info', code, vars)
}

/** Convenience: translate a UI / component copy code. */
export function tUi(code: string, vars?: Record<string, string | number>): string {
  return t('ui', code, vars)
}

/** Current active locale string (e.g. 'en', 'hi'). */
export function getLocale(): string {
  return _locale
}
