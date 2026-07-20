/**
 * Jest config for prana-mobile (React Native / Expo SDK 56).
 *
 * Uses the `jest-expo` preset, which wires up the RN/Expo transforms,
 * transformIgnorePatterns, and native-module shims. We layer on:
 *  - moduleNameMapper for the `@/*` path aliases (mirrors tsconfig `paths`),
 *    plus an explicit `@/i18n` → root `i18n/` mapping because the i18n module
 *    lives at the repo root, not under `src/`.
 *  - a setup file for project-specific native-module mocks.
 */
module.exports = {
  preset: 'jest-expo',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  moduleNameMapper: {
    // Order matters — first match wins. Specific aliases before the generic `@/*`.
    '^@/i18n$': '<rootDir>/i18n/index.ts',
    '^@/i18n/(.*)$': '<rootDir>/i18n/$1',
    '^@/assets/(.*)$': '<rootDir>/assets/$1',
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  testMatch: ['**/?(*.)+(test).[jt]s?(x)'],
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    'i18n/**/*.ts',
    '!**/*.d.ts',
    '!**/node_modules/**',
  ],
};
