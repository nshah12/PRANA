/**
 * Tests for the i18n translation helper (pure, zero native deps).
 * Doubles as the smoke test that the Jest + jest-expo harness transforms TS
 * and resolves the `@/i18n`-style root module correctly.
 */
import en from './en.json';
import {
  t, tError, tUi, tInfo, setLocale, getLocale, registerLocale,
} from './index';

describe('i18n translation helper', () => {
  afterEach(() => setLocale('en')); // reset active locale between tests

  it('maps a real code to its locale string', () => {
    expect(t('error', 'INVALID_TOTP')).toBe('Incorrect authenticator code. Please try again.');
  });

  it('falls back to the raw code for an unknown code', () => {
    expect(t('error', 'NO_SUCH_CODE_XYZ')).toBe('NO_SUCH_CODE_XYZ');
  });

  it('falls back to the raw code for an unknown category', () => {
    // @ts-expect-error — intentionally passing an invalid category
    expect(t('not_a_category', 'ANYTHING')).toBe('ANYTHING');
  });

  it('interpolates {vars} into the string', () => {
    // info.SESSION_EXPIRING_SOON = "Your session will expire in {minutes} minutes."
    expect(tInfo('SESSION_EXPIRING_SOON', { minutes: 5 })).toBe(
      'Your session will expire in 5 minutes.',
    );
  });

  it('tError and tUi delegate to the right category', () => {
    expect(tError('INVALID_TOTP')).toBe(t('error', 'INVALID_TOTP'));
    // Every ui key resolves to a non-code string (not the raw key back).
    const firstUiKey = Object.keys(en.ui)[0];
    expect(tUi(firstUiKey)).not.toBe(firstUiKey);
  });

  it('setLocale falls back to en for an unregistered locale', () => {
    setLocale('zz');
    expect(getLocale()).toBe('zz');
    expect(t('error', 'INVALID_TOTP')).toBe('Incorrect authenticator code. Please try again.');
  });

  it('registerLocale + setLocale switches the active locale', () => {
    registerLocale('xx', { ...en, error: { ...en.error, INVALID_TOTP: 'XX-CODE' } } as typeof en);
    setLocale('xx');
    expect(t('error', 'INVALID_TOTP')).toBe('XX-CODE');
  });
});
