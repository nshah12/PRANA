/**
 * PRANA Mobile — typed translation helper (React Native / Expo).
 *
 * Zero runtime dependencies. No i18n library.
 * Locale JSON is bundled by Metro at build time — no async loading needed.
 *
 * Usage:
 *   import { t, tError, tSuccess, tStatus, tValidation } from '@/i18n'
 *   t('error', 'INVALID_TOTP')                         // → "Incorrect authenticator code. Please try again."
 *   t('success', 'DOC_UPLOADED')                       // → "Document uploaded. Processing will begin shortly."
 *   t('info', 'SESSION_EXPIRING_SOON', { minutes: 5 }) // → "Your session will expire in 5 minutes."
 *   tStatus('QUEUED')                                  // → "Queued"
 *   tValidation('FIELD_REQUIRED')                      // → "This field is required."
 */

import en from './en.json'

export type MessageCategory =
  | 'error'
  | 'success'
  | 'info'
  | 'validation'
  | 'status'
  | 'pipeline_error'
  | 'ask_error'
  | 'ui'

type LocaleData = typeof en

const LOCALES: Record<string, LocaleData> = { en }

let _active: LocaleData = en
let _locale = 'en'

/**
 * Switch active locale. Call once at app startup from user preference.
 * If locale JSON is not registered, falls back to 'en' silently.
 */
export function setLocale(locale: string): void {
  _locale = locale
  _active = LOCALES[locale] ?? en
}

export function getLocale(): string {
  return _locale
}

/**
 * Translate a typed code to a display string.
 *
 * @param category - Message category (error, success, info, etc.)
 * @param code     - Typed code string (e.g. 'INVALID_TOTP')
 * @param vars     - Optional interpolation variables ({minutes: 5} → replaces {minutes})
 * @returns        - Translated string, or the raw code as safe fallback
 */
export function t(
  category: MessageCategory,
  code: string,
  vars?: Record<string, string | number>,
): string {
  const section = (_active as Record<string, Record<string, string>>)[category]
  if (!section) return code

  let str = section[code]
  if (!str) return code

  if (vars) {
    for (const [key, value] of Object.entries(vars)) {
      str = str.replaceAll(`{${key}}`, String(value))
    }
  }

  return str
}

export function tError(code: string, vars?: Record<string, string | number>): string {
  return t('error', code, vars)
}

export function tSuccess(code: string, vars?: Record<string, string | number>): string {
  return t('success', code, vars)
}

export function tStatus(code: string): string {
  return t('status', code)
}

export function tValidation(code: string, vars?: Record<string, string | number>): string {
  return t('validation', code, vars)
}

export function tInfo(code: string, vars?: Record<string, string | number>): string {
  return t('info', code, vars)
}

export function tPipelineError(code: string): string {
  return t('pipeline_error', code)
}

export function tAskError(code: string): string {
  return t('ask_error', code)
}

export function tUi(code: string, vars?: Record<string, string | number>): string {
  return t('ui', code, vars)
}

/**
 * Register a new locale at runtime (e.g. lazy-loaded after app boot).
 * Call before setLocale(locale).
 */
export function registerLocale(locale: string, data: LocaleData): void {
  LOCALES[locale] = data
}
