/**
 * Jest setup — project-specific native-module mocks.
 *
 * jest-expo already mocks most Expo/RN native modules. Add anything the app
 * touches that needs deterministic behaviour in tests here.
 */

// AsyncStorage ships an official in-memory Jest mock.
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

// SecureStore (used by src/lib/auth-store) — in-memory stub.
jest.mock('expo-secure-store', () => {
  const store = new Map();
  return {
    getItemAsync: jest.fn(async (k) => (store.has(k) ? store.get(k) : null)),
    setItemAsync: jest.fn(async (k, v) => { store.set(k, String(v)); }),
    deleteItemAsync: jest.fn(async (k) => { store.delete(k); }),
  };
});
