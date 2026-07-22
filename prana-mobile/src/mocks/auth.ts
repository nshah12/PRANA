export const mockAuth = {
  isAuthenticated: false,   // toggle to true to skip auth flow
  hasDeviceCredential: false, // true -> start at BiometricUnlock instead of SignIn
  hasTotpConfigured: false,  // false -> show TotpSetup after SignIn
};
